from app.models import User
from app.utils.bases import BaseResource

class UserResource(BaseResource[User]):

    fields = ("id", "name", "email", "created_at")

    def additional ( self, model: User ) -> dict[str, object]:
        return { "roles": model.role_names() } if "roles" in model.related else {}
