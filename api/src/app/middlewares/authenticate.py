from core.http import Request
from app.models import User
from app.services import AuthService

class Authenticate:

    def __init__ ( self, service: AuthService ) -> None:

        self._service = service

    async def __call__ ( self, request: Request ) -> User:

        user = await self._service.identify(request.header("authorization") or None)

        request.assign(user=user)

        return user
