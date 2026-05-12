from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    url: str = Field()
