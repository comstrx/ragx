from app.models import User
from app.support.bases import BaseResource


class UserResource(BaseResource[User]):

    fields = ("id", "name", "role", "created_at")
