# ----- library import -----
from typing import Optional, Union
from pydantic import BaseModel


class Product(BaseModel):
    title: str
    price: Optional[float] = None
    ratings: Optional[float] = None
    reviews_count: Optional[int] = None
    description: Union[list[str], str]
    variants: Optional[list[dict]] = None

    def to_dict(self) -> dict:
        return self.model_dump()
