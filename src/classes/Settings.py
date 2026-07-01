# ----- library import -----
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # ----- ENV config -----
    ENV: str = Field(..., env="ENV")

    # ----- log config -----
    LOG_LEVEL: str = Field(..., env="LOG_LEVEL")

    # ----- login credentials -----
    AMAZON_EMAIL: str = Field(..., env="AMAZON_EMAIL")
    AMAZON_PASSWORD: str = Field(..., env="AMAZON_PASSWORD")

    # ----- limit config -----
    THRESHOLD_LIMIT: int = Field(default=200, env="THRESHOLD_LIMIT")


settings = Settings()
