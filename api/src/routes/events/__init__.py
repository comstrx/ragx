from app.events import UserRegistered
from app.listeners import SendWelcomeMail

listeners = {
    UserRegistered: (SendWelcomeMail,),
}

__all__ = ["listeners"]
