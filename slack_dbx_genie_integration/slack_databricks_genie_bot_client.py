from typing import Optional
from cachetools import TTLCache
import threading
import logging

import re
import json
import polars as pl

from slack_bolt import App, Say
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from databricks_genie_client import DbxGenieClient, DbxGenieQueryResults

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class SlackGenieBotCache:
    """
    Thread-safe TTL Cache for storing short-lived states like conversation mapping.
    """
    def __init__(self, maxsize=100, ttl=60*60*24):
        """
        Initialize the cache with a maximum size and time-to-live (ttl) in seconds.
        """
        logger.debug(f"Initializing SlackGenieBotCache with maxsize={maxsize}, ttl={ttl}s")
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.lock = threading.Lock()
    
    def get_item(self,key):
        """
        Retrieve an item from the cache
        """
        with self.lock:
            return self.cache.get(key,None)
    
    def set_item(self,key,value):
        """
        Set an item in the cache
        """
        with self.lock:
            self.cache[key] = value
    
    def delete_item(self,key):
        """
        Delete an item from the cache if it exists
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]

class SlackDbxGenieBotClient:
    """
    The main Slack application client for the Databricks Genie bot.
    Wires up Slack events to Databricks Genie queries.
    """
    
    def __init__(
        self, 
        slack_app_token:str, 
        slack_bot_token:str, 
        slack_signing_secret:str, 
        dbx_genie_client:DbxGenieClient,
        cache: Optional[SlackGenieBotCache] = None,
        **kwargs
        ):
        """
        Initialize the Slack bot, register event listeners, and set up caching.
        """
        logger.info("Initializing SlackDbxGenieBotClient...")
        self.slack_app_token = slack_app_token
        self.slack_bolt_app = App(token=slack_bot_token, signing_secret=slack_signing_secret)
        self.slack_client = WebClient(token=slack_bot_token)
        self.dbx_genie_client = dbx_genie_client
        if not cache:
            cache = SlackGenieBotCache(maxsize=1000)
        self.cache = cache
        
        self.genie_timeout_seconds = kwargs.get("genie_timeout_seconds", 60*5)
        self.genie_result_limit = kwargs.get("genie_result_limit", 50000)

        
        @self.slack_bolt_app.command("/askgenie")
        def _askgenie_command(ack, body, client: WebClient, command):
            """
            Handler for the /askgenie slack slash command.
            Acknowledges the command and opens a modal view for user input.
            """
            ack()
            
            channel_id = body.get("channel_id")
            user_id = body.get("user_id")
            user_info = client.users_info(user=user_id)
            user_name = user_info.get("user",{}).get("name","")
            user_email = user_info.get("user",{}).get("email","")
            text = command.get("text","")
            
            logger.debug(f"/askgenie invoked by user: {user_name} ({user_id}) in channel {channel_id}")
            
            logger.info("Opening /askgenie modal view.")
            client.views_open(
                trigger_id=body.get("trigger_id"),
                view=SlackDbxGenieBotClient._build_askgenie_view(channel_id=channel_id, default_text=text)
            )
        
        @self.slack_bolt_app.view("askgenie_view")
        def _askgenie_view(ack, body, client: WebClient, view):
            """
            Handler for the submission of the /askgenie modal view.
            Delegates logic to the `handle_askgenie_command` method.
            """
            ack()
            logger.info("Received submission from askgenie_view modal.")
            self.handle_askgenie_command(body, client, view)
            
        @self.slack_bolt_app.event("app_mention")
        def _handle_app_mention(event, say: Say, client: WebClient):
            """
            Handler for standard Slack @mentions of the bot.
            Delegates logic to the `handle_mention` method.
            """
            logger.info(f"Received app_mention event from user {event.get('user', 'unknown')}")
            self.handle_mention(event, say, client)
            
        @self.slack_bolt_app.event("message")
        def _handle_message(event, say: Say, client: WebClient):
            """
            Pass-through handler for regular channel/DM messages.
            Currently unhandled, but ensures the bot doesn't crash on standard messages.
            """            
            pass
        
        @self.slack_bolt_app.action("feedback_positive")
        @self.slack_bolt_app.action("feedback_negative")
        def _handle_genie_feedback(ack, body, client: WebClient):
            """
            Handler for the thumbs-up / thumbs-down inline feedback buttons.
            Submits sentiment to Genie and prompts the user for a text comment.
            """
            ack()
            logger.info("Received thumbs-up/down inline feedback action.")
            channel_id = body.get("channel", {}).get("id")
            message_ts = body.get("message", {}).get("ts")
            
            actions = body.get("actions",[{}])[0]
            
            feedback_value = json.loads(actions.get("value",{}))
            
            sentiment = feedback_value.get("sentiment")
            genie_conversation_id = feedback_value.get("conversation_id")
            genie_message_id = feedback_value.get("message_id")
            
            logger.info(f"Submitting '{sentiment}' sentiment for conversation_id={genie_conversation_id}, message_id={genie_message_id}")
            feedback_submitted = self.dbx_genie_client.send_message_feedback(
                conversation_id=genie_conversation_id,
                message_id=genie_message_id,
                feedback=sentiment
            )
            
            if feedback_submitted:
                logger.info(f"Feedback submitted for conversation_id: {genie_conversation_id}, message_id: {genie_message_id}, feedback: {sentiment}")
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"Thanks for your feedback! You submitted *{sentiment}* feedback for this response."
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": ":speech_balloon: Add Comment"
                                    },
                                    "action_id": "feedback_comment",
                                    "value": json.dumps(
                                        {
                                            "genie_conversaiton_id": genie_conversation_id,
                                            "genie_message_id": genie_message_id,
                                            "sentiment": sentiment
                                        }
                                    )
                                }
                            ]
                        }
                    ]
                )
            else:
                logger.error(f"Failed to submit feedback for conversation_id: {genie_conversation_id}, message_id: {genie_message_id}, feedback: {sentiment}")
                client.chat_postMessage(
                    channel=channel_id,
                    ts=message_ts,
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"Sorry, there was an error submitting your feedback. Please try again later."
                            }
                        }
                    ],
                    text=f"Sorry, there was an error submitting your feedback. Please try again later."
                )       
        
        @self.slack_bolt_app.action("feedback_comment")
        def _handle_feedback_comment_modal(ack, body, client: WebClient):
            """
            Handler for the "Add Comment" button that appears after leaving feedback.
            Opens a modal dialog allowing the user to type explicit feedback text.
            """
            ack()
            logger.info("Opening 'Add Comment' modal for extended feedback.")
            
            actions = body.get("actions",[{}])[0]
            feedback_value = json.loads(actions.get("value",{}))
            
            modal_metadata = json.loads(actions.get("value",{}))
            modal_metadata["channel_id"] = body.get("channel", {}).get("id")
            modal_metadata["message_ts"] = body.get("message", {}).get("ts")
            
            client.views_open(
                trigger_id=body.get("trigger_id"),
                view={
                    "type": "modal",
                    "callback_id": "feedback_comment_submit",
                    "private_metadata": json.dumps(modal_metadata),
                    
                    "title": {
                        "type": "plain_text",
                        "text": "Add Genie Comment"
                    },
                    "submit": {
                        "type": "plain_text",
                        "text": "Submit"
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "Cancel"
                    },
                    "blocks": [
                        {
                            "type": "input",
                            "block_id": "feedback_comment_block",
                            "label": {
                                "type": "plain_text",
                                "text": "Share your thoughts about this response to help us improve!"
                            },
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "feedback_comment_input",
                                "multiline": True,
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Type your comment here..." 
                                }
                            }
                        }
                    ]
                }
            )
            
            return
        
        @self.slack_bolt_app.view("feedback_comment_submit") 
        def _handle_feedback_comment_submit(ack, body, client: WebClient):
            """
            Handler for when the user submits the extended text feedback modal.
            Sends the text string back to Databricks Genie context.
            """
            ack()
            modal_metadata = json.loads(body.get("view",{}).get("private_metadata","{}"))
            comment = body.get("view",{}).get("state",{}).get("values",{}).get("feedback_comment_block",{}).get("feedback_comment_input",{}).get("value","")
            genie_conversation_id = modal_metadata.get("genie_conversaiton_id")
            genie_message_id = modal_metadata.get("genie_message_id")
            
            logger.info(f"Submitting comment to Genie: conversation_id={genie_conversation_id}, message_id={genie_message_id}")
            feedback_submitted = self.dbx_genie_client.add_message_comment(
                comment=comment, 
                conversation_id=genie_conversation_id, 
                message_id=genie_message_id
            )
            
            channel_id = modal_metadata.get("channel_id")
            message_ts = modal_metadata.get("message_ts")
            
            if channel_id and message_ts:
                logger.debug(f"Updating Slack UI in channel {channel_id} with comment confirmation.")
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Thanks for your feedback and comment!*"
                            }
                        }
                    ],
                    text=f"Thanks for your feedback and comment!"
                )
            return       
        
        
    @staticmethod
    def _build_text_input_block(
        block_id: str,
        action_id:str,
        label:str,
        placeholder:str,
        multiline:bool = False,
        optional:bool = False,
        initial_value: Optional[str] = None
        ):
        """
        Helper method to build a standard Slack Block Kit text input element.
        """
        logger.debug(f"Building text input block with block_id='{block_id}', action_id='{action_id}'")
        block = {
            "type": "input",
            "block_id": block_id,
            "label": {
                "type": "plain_text",
                "text": label
            },
            "element": {
                "type": "plain_text_input",
                "action_id": action_id,
                "placeholder": {
                    "type": "plain_text",
                    "text": placeholder
                },
                "multiline": multiline,
            }
        }
        if initial_value: block["element"]["initial_value"] = initial_value
        if optional: block["optional"] = True
        return block
    
    def _send_feedback_message(self, channel_id: str, thread_ts: str, client: WebClient, genie_conversation_id: str, genie_message_id: str):
        """
        Sends the inline feedback message containing Yes/No buttons prompting users to rate the response.
        """
        logger.info(f"Sending inline feedback prompt to channel '{channel_id}', thread '{thread_ts}'")
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Was this response helpful?*"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": ":thumbsup: Yes"
                        },
                        "action_id": "feedback_positive",
                        "value": json.dumps({"sentiment":"positive","conversation_id": genie_conversation_id, "message_id": genie_message_id})
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": ":thumbsdown: No"
                        },
                        "action_id": "feedback_negative",
                        "value": json.dumps({"sentiment":"negative","conversation_id": genie_conversation_id, "message_id": genie_message_id})
                    }
                ]
            }
        ]
        
        try:
            response = client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=blocks,
                text="Was this response helpful?"
            )
            return response
        except Exception as e:
            logger.error(f"Failed to post feedback prompt: {e}")
            return None
        
    
    @staticmethod
    def _build_askgenie_view(channel_id: str, default_text: str):
        """
        Builds the layout (View object) for the /askgenie modal.
        """
        return {
            "type": "modal",
            "callback_id": "askgenie_view",
            "title": {
                "type": "plain_text",
                "text": "Ask Databricks Genie"
            },
            "submit": {
                "type": "plain_text",
                "text": "Ask"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "private_metadata": channel_id,
            "blocks": [
                SlackDbxGenieBotClient._build_text_input_block(
                    block_id="askgenie_block",
                    action_id="askgenie_action",
                    label="Ask Genie",
                    placeholder="Type your question here...",
                    initial_value=default_text,
                    multiline=True
                )
            ]
        }
    
    def _convert_standard_markdown_to_slack_markdown(self, text: str):
        """
        Converts standard GitHub-flavored markdown responses into Slack's specific mrkdwn format.
        (e.g., standardizes asterisks, lists, links, sizing)
        """
        # 1. Italic (standard md allows *text* for italic, Slack uses _text_ for italic)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'_\1_', text)
        # 2. Bold (standard md uses **text** or __text__, Slack uses *text* for bold)
        text = re.sub(r'(\*\*|__)(.+?)\1', r'*\2*', text)
        # 3. Code blocks (strip language tags like ```python -> ```)
        text = re.sub(r'```[a-zA-Z0-9_+\-]*\n', '```\n', text)
        # 4. Headers (convert # Header to *Header* for Slack)
        text = re.sub(r'(?m)^#{1,6}\s+(.+)', r'*\1*', text)
        # 5. Unordered lists (convert bullet points like - or * to •)
        text = re.sub(r'(?m)^(\s*)[*+-]\s+', r'\1• ', text)
        # 6. Ordered lists (ensure consistent 1. spacing)
        text = re.sub(r'(?m)^(\s*)(\d+)\.\s+', r'\1\2. ', text)
        # 7. Links (convert [Text](URL) to <URL|Text>)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', text)
        
        return text

    def _convert_query_results_to_dataframe(self, query_results: DbxGenieQueryResults) -> pl.DataFrame:
        columns = {col.name: col.type_text for col in query_results.query_results_schema.columns}
        rows = query_results.data_rows
        
        df = pl.DataFrame(
            data=rows,
            schema=list(columns.keys()),
            orient="row",
            strict=False
        )
        
        return df

    def _upload_df_as_csv(self,df: pl.DataFrame, channel_id: str, thread_ts: str, client: WebClient, filename: str = "query_results.csv", title: str = "Query Results"):
        """
        Upload a Polars DataFrame to a Slack thread as a CSV file attachment.
        """
        logger.info(f"Uploading dataframe as '{filename}' to channel {channel_id}, thread {thread_ts}")
        try:
            csv_bytes = df.write_csv().encode("utf-8")
            client.files_upload_v2(
                channel=channel_id,
                thread_ts=thread_ts,
                content=csv_bytes,
                filename=filename,
                title=title or filename
            ) 
            logger.info("Successfully uploaded CSV to Slack.")
        except Exception as e:
            logger.error(f"Failed to upload CSV to Slack: {e}")
    
    def handle_askgenie_command(self, body, client: WebClient, view):
        """
        Handles the submission of the /askgenie modal view.
        Sends the question to Genie and posts the response to the specified channel.
        """
        user_id = body.get("user", {}).get("id")
        channel_id = view["private_metadata"]
        question = view["state"]["values"]["askgenie_block"]["askgenie_action"]["value"]
        
        logger.info(f"Handling /askgenie command from user {user_id} in channel {channel_id}. Question: '{question}'")
        
        user_info = client.users_info(user=user_id)
        user_name = user_info.get("user", {}).get("name", "")
        user_email = user_info.get("user", {}).get("email", "")
        
        acknowledge_message = client.chat_postMessage(channel=channel_id, text=f"Hi <@{user_id}>, thanks for the question: *{question}* let me look into it... :thinking_face:")
        message_ts = acknowledge_message.get("message", {}).get("ts",None)
        
        if message_ts: genie_conversation_id = self.cache.get_item(f"conversation:{message_ts}")
        else: genie_conversation_id = None
        
        genie_response = self.dbx_genie_client.ask_question(
            question=question,
            conversation_id=genie_conversation_id,
            timeout=self.genie_timeout_seconds,
            result_limit=self.genie_result_limit
        )
        if not genie_response.success or not genie_response.response_text:
            logger.error(f"Genie did not return a result for question: {question}, error: {genie_response.error}")
            client.chat_postMessage(channel=channel_id, thread_ts=message_ts, text=f"Sorry <@{user_id}>, I wasn't able to get a response from Genie for your question: *{question}* :cry: - please try again later.")
            return
        
        genie_conversation_id = genie_response.conversation_id
        genie_message_id = genie_response.message_id
        
        self.cache.set_item(f"conversation:{message_ts}", genie_conversation_id)
        
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": self._convert_standard_markdown_to_slack_markdown(genie_response.response_text or "")
                    }
                }
            ]
        )
        
        if genie_response.suggested_questions:
            suggested_questions_text = "\n".join([f"* {q}" for q in genie_response.suggested_questions])
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Suggested Questions:*\n{suggested_questions_text}"
                        }
                    }
                ]
            )
        
        if genie_response.query and genie_response.query.query:
            query_results = genie_response.query.results
            if query_results:
                df = self._convert_query_results_to_dataframe(query_results)
                self._upload_df_as_csv(
                    df=df,
                    channel_id=channel_id,
                    thread_ts=message_ts,
                    client=client
                ) 
            
            query_text = genie_response.query.query
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Query:*\n```{query_text}```"
                        }
                    }
                ]
            )   
        self._send_feedback_message(
            channel_id=channel_id,
            thread_ts=message_ts,
            client=client,
            genie_conversation_id=genie_conversation_id,
            genie_message_id=genie_message_id
        )    
    
    def handle_mention(self, event, say: Say, client: WebClient):
        """
        Handles cases where the bot is mentioned (@botname).
        Cleans the text, triggers a Genie query, and replies in the same thread.
        """
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        
        logger.info(f"Handling mention event from user {user_id} in channel {channel_id}")
        
        # Clean the bot mention from the text (e.g., <@U12345678>)
        question = re.sub(r'<@\w+>\s*', '', text).strip()
        
        if not question:
            if not question:
                client.chat_postMessage(
                    channel=channel_id, 
                    thread_ts=thread_ts,
                    text=f"Hi <@{user_id}>, I'm here to help. Either ask a question or use the `/askgenie` command to get started! :slightly_smiling_face:"
                )
            
        # Reply in a thread if it's already one, otherwise use the message ts to start a thread
        thread_ts = event.get("thread_ts", event.get("ts"))
        
        acknowledge_message = client.chat_postMessage(
            channel=channel_id, 
            thread_ts=thread_ts,
            text=f"Hi <@{user_id}>, thanks for the question: *{question}* let me look into it... :thinking_face:"
        )
        
        genie_conversation_id = self.cache.get_item(f"conversation:{thread_ts}")
        
        genie_response = self.dbx_genie_client.ask_question(
            question=question,
            conversation_id=genie_conversation_id,
            timeout=self.genie_timeout_seconds,
            result_limit=self.genie_result_limit
        )
        
        if not genie_response.success or not genie_response.response_text:
            logger.error(f"Genie did not return a result for question: {question}, error: {genie_response.error}")
            client.chat_postMessage(
                channel=channel_id, 
                thread_ts=thread_ts, 
                text=f"Sorry <@{user_id}>, I wasn't able to get a response from Genie for your question: *{question}* :cry: - please try again later."
            )
            return

        genie_conversation_id = genie_response.conversation_id
        genie_message_id = genie_response.message_id
        
        self.cache.set_item(f"conversation:{thread_ts}", genie_conversation_id)
        
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": self._convert_standard_markdown_to_slack_markdown(genie_response.response_text or "")
                    }
                }
            ]
        )
        
        if genie_response.suggested_questions:
            suggested_questions_text = "\n".join([f"* {q}" for q in genie_response.suggested_questions])
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Suggested Questions:*\n{suggested_questions_text}"
                        }
                    }
                ]
            )
        
        if genie_response.query and genie_response.query.query:
            query_results = genie_response.query.results
            if query_results:
                df = self._convert_query_results_to_dataframe(query_results)
                self._upload_df_as_csv(
                    df=df,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    client=client
                ) 
            
            query_text = genie_response.query.query
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Query:*\n```{query_text}```"
                        }
                    }
                ]
            )   
            
        self._send_feedback_message(
            channel_id=channel_id,
            thread_ts=thread_ts,
            client=client,
            genie_conversation_id=genie_conversation_id,
            genie_message_id=genie_message_id
        )
    
    def start(self):
        """
        Main entry point to start the Slack socket mode listener.
        Connects the bot to Slack and listens for incoming Socket Mode events indefinitely.
        """
        import time
        logger.info("Starting Slack Genie Bot...")
        handler = SocketModeHandler(self.slack_bolt_app, self.slack_app_token)
        handler.connect()
        
        logger.info("Slack Genie Bot connected...")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Shutting down Slack Genie Bot...")
            handler.close()