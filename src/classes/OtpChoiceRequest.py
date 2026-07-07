# ----- library import -----
from pydantic import BaseModel, Field


class OtpChoiceRequest(BaseModel):
    choice: str = Field(
        min_length=1,
        description="The OTP delivery method (e.g. 'WhatsApp me at my number ending in 388') selected by the user in the dashboard popup",
    )