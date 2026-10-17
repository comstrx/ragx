from pydantic import Field

from app.utils.bases import BaseRequest

class RefreshRequest(BaseRequest):

    refresh_token: str = Field(min_length=16, max_length=4096)
