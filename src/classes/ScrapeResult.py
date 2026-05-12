from typing import Optional

from pydantic import BaseModel

from .Product import Product
from .ScrapeFailReason import ScrapeFailReason


class ScrapeResult(BaseModel):
    product: Optional[Product] = None
    success: bool = False
    reason: Optional[ScrapeFailReason] = None
    detail: str = ""
