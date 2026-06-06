from pprint import pp
from databricks_genie_client import DbxGenieClient
from slack_databricks_genie_bot_client import SlackDbxGenieBotClient, SlackGenieBotCache

from config import config


dbx_genie_client = DbxGenieClient(
    space_id=config.databricks_genie_space_id
)
slack_cache = SlackGenieBotCache(maxsize=1000)
slack_genie_client = SlackDbxGenieBotClient(
    slack_app_token=config.slack_app_token.get_secret_value(),
    slack_bot_token=config.slack_bot_token.get_secret_value(),
    slack_signing_secret=config.slack_signing_secret.get_secret_value(),
    dbx_genie_client=dbx_genie_client,
    cache=slack_cache
)

slack_genie_client.start()