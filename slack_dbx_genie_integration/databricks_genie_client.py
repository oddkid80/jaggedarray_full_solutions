import logging
from typing import Optional
from pprint import pp
from datetime import timedelta
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import GenieMessage, GenieGetMessageQueryResultResponse, GenieFeedbackRating
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class DbxGenieQueryResultsSchemaColumn(BaseModel):
    name: str
    type_text: str
    type_name: str
    position: int

class DbxGenieQueryResultsSchema(BaseModel):
    column_count: int
    columns: list[DbxGenieQueryResultsSchemaColumn]

class DbxGenieQueryResults(BaseModel):
    query_results_schema: DbxGenieQueryResultsSchema
    data_rows: list
    total_rows: int
    truncated: bool = Field(default=False)

class DbxGenieQueryResponse(BaseModel):
    query: str
    results: Optional[DbxGenieQueryResults] = None
    
class DbxGenieResponse(BaseModel):
    success: bool
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    response_text: Optional[str] = None
    suggested_questions: Optional[list] = None
    query: Optional[DbxGenieQueryResponse] = None
    raw_response: Optional[dict] = None
    error: Optional[str] = None

class DbxGenieClient:
    """
    Client to interact with Databricks Genie spaces.
    Handles creating conversations, sending messages, and parsing results.
    """
    
    def __init__(self,space_id: str,):
        """
        Initialize the Databricks Genie Client.
        
        Args:
            space_id (str): The ID of the Genie space to connect to.
        """
        logger.info(f"Initializing DbxGenieClient for space_id: {space_id}")
        self.databricks_client = WorkspaceClient()
        self.space_id = space_id
    
    def _pull_sql_results(self, conversation_id: str, message_id: str, attachment_id: str, result_limit: int = 100) -> GenieGetMessageQueryResultResponse:
        """
        Fetch SQL query results from a Genie message attachment.
        
        Args:
            conversation_id (str): The conversation ID.
            message_id (str): The specific message ID.
            attachment_id (str): The attachment ID containing the query results.
            result_limit (int): The maximum number of rows to retrieve.
            
        Returns:
            DbxGenieQueryResults: Parsed schema and rows.
        """
        logger.info(f"Fetching SQL results for attachment {attachment_id} in conversation {conversation_id}")
        next_url = f"{self.databricks_client.config.host}/api/2.0/genie/spaces/{self.space_id}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
        result = self.databricks_client.api_client.do(method="GET", url=next_url)
        if not result:
            logger.warning(f"No results found for query attachment {attachment_id} in message {message_id} of conversation {conversation_id}")
            return None
        else:
            statement_response = result.get("statement_response",{})
            
            total_rows = statement_response.get("manifest",{}).get("total_row_count",0)
            schema = statement_response.get("manifest",{}).get("schema",{})
            data_rows = statement_response.get("result",{}).get("data_array",[])
            
            if len(data_rows) > result_limit:
                logger.info(f"Result has {total_rows} rows, but limiting to {result_limit} rows")
                
                return DbxGenieQueryResults(
                    query_results_schema=DbxGenieQueryResultsSchema(
                        column_count=schema.get("column_count",0),
                        columns=[DbxGenieQueryResultsSchemaColumn(**col) for col in schema.get("columns",[])]
                    ),
                    data_rows=data_rows[:result_limit],
                    total_rows=total_rows,
                    truncated=True
                )
                
            next_url = statement_response.get("result",{}).get("next_chunk_internal_link",None)            
            while next_url and len(data_rows) < total_rows and len(data_rows) < result_limit:
                logger.debug(f"Fetching additional result chunk: {next_url}")
                result = self.databricks_client.api_client.do(method="GET", url=next_url)
                if not result:
                    break
                statement_response = result.get("statement_response",{})
                data_rows.extend(statement_response.get("result",{}).get("data_array",[]))
                next_url = statement_response.get("result",{}).get("next_chunk_internal_link",None)
        
        return DbxGenieQueryResults(
            query_results_schema=DbxGenieQueryResultsSchema(
                column_count=schema.get("column_count",0),
                columns=[DbxGenieQueryResultsSchemaColumn(**col) for col in schema.get("columns",[])]
            ),
            data_rows=data_rows,
            total_rows=total_rows,
            truncated=len(data_rows) >= result_limit
        )
    
    def send_message_feedback(self, conversation_id: str, message_id: str, feedback: str) -> bool:
        """
        Submit thumbs up/down feedback for a specific Genie message.
        
        Args:
            conversation_id (str): The conversation ID.
            message_id (str): The message ID.
            feedback (str): 'POSITIVE' or 'NEGATIVE'.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        feedback = feedback.upper()
        if feedback not in ["POSITIVE", "NEGATIVE"]:
            logger.error(f"Invalid feedback value: {feedback}. Must be 'POSITIVE' or 'NEGATIVE'")
            return False
        
        logger.info(f"Sending {feedback} feedback for message {message_id} in conversation {conversation_id}")
        self.databricks_client.genie.send_message_feedback(
            space_id=self.space_id,
            conversation_id=conversation_id,
            message_id=message_id,
            rating=GenieFeedbackRating(value=feedback)
        )
        return True

    def add_message_comment(self, conversation_id: str, message_id: str, comment: str) -> bool:
        """
        Add a textual comment/feedback to a specific Genie message.
        
        Args:
            conversation_id (str): The conversation ID.
            message_id (str): The message ID.
            comment (str): The feedback text.
            
        Returns:
            bool: True if successful.
        """
        logger.info(f"Adding comment to message {message_id} in conversation {conversation_id}")
        self.databricks_client.genie.create_message_comment(
            space_id=self.space_id,
            conversation_id=conversation_id,
            message_id=message_id,
            content=comment
        )
        return True
    
    def ask_question(self, question: str, conversation_id: Optional[str] = None, timeout: int = 60, result_limit: int = 100) -> DbxGenieResponse:
        """
        Send a question to Databricks Genie and wait for the response.
        Optionally continues an existing conversation.
        
        Args:
            question (str): The question to ask Genie.
            conversation_id (Optional[str]): Existing conversation ID, if any.
            timeout (int): Timeout in seconds to wait for a response.
            result_limit (int): Maximum query rows to return.
            
        Returns:
            DbxGenieResponse: Object containing the parsed Genie response including queries.
        """
        logger.info(f"Asking Genie: '{question}' (conversation_id: {conversation_id})")
        try:
            if conversation_id:
                # Send message as part of an existing conversation 
                response = self.databricks_client.genie.create_message_and_wait(
                    space_id=self.space_id,
                    conversation_id=conversation_id,
                    content=question,
                    timeout=timedelta(seconds=timeout),
                )
            else:
                # Start a new conversation
                response = self.databricks_client.genie.start_conversation_and_wait(
                    space_id=self.space_id,
                    content=question,
                    timeout=timedelta(seconds=timeout),
                )
            
            # Retrieves necessary elements of the conversation
            conversation_id = response.conversation_id
            message_id = response.message_id
            attachments = response.attachments
            
            response_text = ""
            suggested_questions = ""
            query_results = []
            query = None
            
            # Loops through Genie "attachments" - which are parts of the response (e.g., text, suggested questions, and query results)
            for a in attachments:
                if a.suggested_questions:
                    suggested_questions = a.suggested_questions.questions
                if a.text:
                    response_text = a.text.content
                if a.query:
                    query = a.query.query
                    query_results = self._pull_sql_results(
                        conversation_id=conversation_id, 
                        message_id=message_id, 
                        attachment_id=a.attachment_id, 
                        result_limit=result_limit
                    )
            
            # Returns our response object
            return DbxGenieResponse(
                success=True,
                conversation_id=conversation_id,
                message_id=message_id,
                response_text=response_text,
                suggested_questions=suggested_questions,
                query=DbxGenieQueryResponse(
                    query=query,
                    results=query_results
                ) if query else None,
                raw_response=response.as_dict()
            )            
            
        except Exception as ex:
            logger.error(f"Error asking question: {ex}")
            return DbxGenieResponse(
                success=False,
                error=str(ex)
            )