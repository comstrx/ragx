from core.broadcast import broadcast
from app.models import User

def owner ( user: User, user_id: str ) -> bool:
    return str(user.id) == user_id

def staff ( user: User ) -> bool:
    return user.has_role("admin")

def present ( user: User, room: str ) -> dict[str, str]:
    return { "id": str(user.id), "name": user.name, "room": room }

broadcast.public("news")
broadcast.channel("users.{user_id}", owner)
broadcast.channel("staff", staff)
broadcast.channel("room.{room}", present)

channels = broadcast.channels()

__all__ = ["channels"]
