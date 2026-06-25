# ----- library import -----
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(
        min_length=1, description="The query string to search for on Amazon"
    )
