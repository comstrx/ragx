from typing import Annotated

from core.http import Inject, Response
from app.middlewares import authenticate
from app.models import User
from app.requests import LoginRequest, RefreshRequest, RegisterRequest
from app.services import AuthService
from app.utils.cycle import Controller

type Actor = Annotated[User, Inject(authenticate)]

class AuthController(Controller):

    def __init__ ( self, service: AuthService ) -> None:

        self._service = service

    async def register ( self, body: RegisterRequest ) -> Response:

        return self.created(await self._service.register(body.name, body.email, body.password))

    async def login ( self, body: LoginRequest ) -> Response:

        return self.ok(await self._service.login(body.email, body.password))

    async def refresh ( self, body: RefreshRequest ) -> Response:

        return self.ok(await self._service.refresh(body.refresh_token))

    async def logout ( self, body: RefreshRequest, user: Actor ) -> Response:

        await self._service.logout(body.refresh_token, user)

        return self.ok()

    async def me ( self, user: Actor ) -> Response:

        return self.ok(await self._service.me(user))
