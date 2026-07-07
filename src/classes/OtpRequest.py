# ----- library import -----
from pydantic import BaseModel, Field


class OtpRequest(BaseModel):
    otp: str = Field(min_length=1, max_length=12, description="OTP code entered by the user in the dashboard popup")