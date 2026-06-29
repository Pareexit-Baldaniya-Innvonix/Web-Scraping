# ----- library import -----
from typing import List, Optional
from pydantic import BaseModel

# ----- local import -----
from .Review import Review


class Product(BaseModel):
    asin: str
    title: str
    image: Optional[List[str]] = None
    price: Optional[float] = None
    ratings: Optional[float] = None
    ratings_count: Optional[int] = None
    description: str
    variants: Optional[List[dict]] = None
    total_reviews: int = 0
    reviews: List[Review]

    def to_dict(self) -> dict:
        return self.model_dump()
