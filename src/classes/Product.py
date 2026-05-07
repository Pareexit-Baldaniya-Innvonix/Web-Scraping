# ----- library import -----
from typing import Optional, Union
from pydantic import BaseModel, Field


class Product(BaseModel):
    title: str
    price: Optional[float]
    ratings: float
    reviews_count: Optional[int]
    description: Union[list[str], str]
    variants: Optional[list[dict]] = Field(default=None)

    def to_dict(self) -> dict:
        return self.model_dump()
