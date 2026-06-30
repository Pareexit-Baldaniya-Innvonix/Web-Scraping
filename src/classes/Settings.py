# ----- library import -----
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    ENV: str = os.getenv("ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    AMAZON_EMAIL: str = os.getenv("AMAZON_EMAIL", "")
    AMAZON_PASSWORD: str = os.getenv("AMAZON_PASSWORD", "")
    THRESHOLD_LIMIT: int = os.getenv("THRESHOLD_LIMIT", 500)


settings = Settings()
