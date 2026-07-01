# ----- library import -----
from typing import List, Optional
from pydantic import BaseModel


class Product(BaseModel):
    asin: str
    title: str
    image: Optional[List[str]] = None
    price: Optional[float] = None
    ratings: Optional[float] = None
    ratings_count: Optional[int] = None
    description: str
    variants: Optional[List[dict]] = None

    def to_dict(self) -> dict:
        return self.model_dump()
