# ----- library import -----
from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=1)
