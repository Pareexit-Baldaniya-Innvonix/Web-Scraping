# ----- library import -----
from typing import Optional, Union
from pydantic import BaseModel

# ----- local import -----
from .Review import Review


class Product(BaseModel):
    title: str
    image: Optional[list[str]] = None
    price: Optional[float] = None
    ratings: Optional[float] = None
    ratings_count: Optional[int] = None
    description: Union[list[str], str]
    variants: Optional[list[dict]] = None
    reviews: Optional[list[Review]] = None

    def to_dict(self) -> dict:
        return self.model_dump()
