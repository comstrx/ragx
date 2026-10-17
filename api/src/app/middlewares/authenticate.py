from typing import Annotated

from core.http import Header, Request
from app.models import User
from app.services import AuthService

class Authenticate:

    def __init__ ( self, service: AuthService ) -> None:

        self._service = service

    async def __call__ ( self, request: Request, authorization: Annotated[str | None, Header()] = None ) -> User:

        user = await self._service.identify(authorization)

        request.state.user = user

        return user
