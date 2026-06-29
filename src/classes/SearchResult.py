# ----- library import -----
from typing import Union
from pydantic import BaseModel


class SearchResult(BaseModel):
    title: str
    price: Union[float, str]
    link: str
    delivery_duration_days: Union[int, str]
