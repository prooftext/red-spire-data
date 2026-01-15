from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    DATABASE_URL: str
    DEBUG: bool = False
    API_VERSION: str = "v1"

settings = Settings()