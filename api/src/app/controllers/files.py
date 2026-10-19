from typing import Annotated

from core.http import Inject, Response, Upload
from app.middlewares import authenticate
from app.models import User
from app.services import FilesService
from app.utils.cycle import Controller

type Actor = Annotated[User, Inject(authenticate)]

class FilesController(Controller):

    def __init__ ( self, service: FilesService ) -> None:

        self._service = service

    async def store ( self, file: Upload, user: Actor ) -> Response:

        return self.created(await self._service.publish(file, user))

    async def keep ( self, file: Upload, user: Actor ) -> Response:

        return self.created(await self._service.keep(file, user))

    async def show ( self, path: str, user: Actor ) -> Response:

        chunks, mime = await self._service.open(path, user)

        return Response.stream(chunks, mime, path.rsplit("/", 1)[-1])
