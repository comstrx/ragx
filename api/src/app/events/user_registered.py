from collections.abc import Sequence
from dataclasses import dataclass

from app.utils.bases import BaseEvent

@dataclass(frozen=True, slots=True)
class UserRegistered(BaseEvent):

    user_id : str
    name    : str
    email   : str

    def channels ( self ) -> Sequence[str]:
        return ("private-staff",)

    def payload ( self ) -> dict[str, object]:
        return { "user_id": self.user_id, "name": self.name }
