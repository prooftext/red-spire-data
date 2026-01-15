from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    DEBUG: bool = False
    API_VERSION: str = "v1"
    
    class Config:
        env_file = ".env"

settings = Settings()