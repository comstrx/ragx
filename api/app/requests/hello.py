from pydantic import Field

from app.support.bases import BaseRequest


class HelloRequest(BaseRequest):

    name: str = Field(default="World", min_length=1, max_length=32, pattern=r"^[\w .'-]+$")
