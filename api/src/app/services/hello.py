from app.enums import Message
from app.repositories import UserRepository
from app.resources import UserResource
from app.utils.bases import BaseService

class HelloService(BaseService):

    def __init__ ( self, users: UserRepository, resource: UserResource ) -> None:

        super().__init__()

        self._users    = users
        self._resource = resource

    async def greet ( self, name: str ) -> dict[str, object]:

        user = await self._users.find_by_name(name)

        self.log.debug("hello.greeted", name=name, known=user is not None)

        return {
            "message" : Message.HELLO.render(name=user.name if user else name),
            "user"    : self._resource.maybe(user),
        }
