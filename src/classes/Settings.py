# ----- library import -----
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    ENV: str = os.getenv("ENV", "development")


settings = Settings()
