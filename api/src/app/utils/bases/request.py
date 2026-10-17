from pydantic import BaseModel, ConfigDict

class BaseRequest(BaseModel):

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True, str_max_length=4096)
