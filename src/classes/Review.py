# ----- library import -----
from pydantic import BaseModel
from typing import Optional


class Review(BaseModel):
    review_number: Optional[int] = None
    reviewer_name: str
    review_date: Optional[str] = None
    review_location: Optional[str] = None
    review_title: Optional[str] = None
    rating: Optional[float] = None
    review_body: Optional[str] = None
    review_helpful: Optional[str] = None
