import os
from typing import Optional, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    databricks_host: str
    databricks_token: Optional[SecretStr] = SecretStr(None)
    databricks_genie_space_id: str
    
    slack_app_token: SecretStr
    slack_bot_token: SecretStr
    slack_signing_secret: SecretStr
    
    def model_post_init(self, context: Any):
        if not os.environ.get("DATABRICKS_HOST") and self.databricks_host: os.environ["DATABRICKS_HOST"] = self.databricks_host        
        if not os.environ.get("DATABRICKS_TOKEN") and self.databricks_token: os.environ["DATABRICKS_TOKEN"] = self.databricks_token.get_secret_value()
    
config = Config()   
    