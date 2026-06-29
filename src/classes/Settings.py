# ----- library import -----
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    ENV: str = os.getenv("ENV", "development")
    AMAZON_EMAIL: Optional[str] = os.getenv("AMAZON_EMAIL", "")
    AMAZON_PASSWORD: Optional[str] = os.getenv("AMAZON_PASSWORD", "")
    THRESHOLD_LIMIT: int = int(os.getenv("THRESHOLD_LIMIT", 500))
    HEADLESS: bool = os.getenv("HEADLESS", "TRUE")


settings = Settings()
