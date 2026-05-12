# ----- library import -----
from typing import Optional
from pydantic import BaseModel

# ----- local import -----
from .Product import Product
from .ScrapeFailReason import ScrapeFailReason


class ScrapeResult(BaseModel):
    product: Optional[Product] = None
    success: bool = False
    reason: Optional[ScrapeFailReason] = None
    detail: str = ""
