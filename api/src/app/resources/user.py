from typing import override
from app.models import User
from app.utils.cycle import Resource

class UserResource(Resource[User]):

    fields: tuple[str, ...] = ("id", "name", "email", "created_at")

    @override
    def additional ( self, model: User ) -> dict[str, object]:

        return { "roles": model.role_names() } if "roles" in model.related else {}
