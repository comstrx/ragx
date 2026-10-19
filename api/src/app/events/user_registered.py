from collections.abc import Sequence
from dataclasses import dataclass
from typing import override

from app.utils.cycle import Event

@dataclass(frozen=True, slots=True)
class UserRegistered(Event):

    user_id : str
    name    : str
    email   : str

    @override
    def channels ( self ) -> Sequence[str]:

        return ("private-staff",)

    @override
    def payload ( self ) -> dict[str, object]:

        return { "user_id": self.user_id, "name": self.name }
