from typing import Annotated

from core.http import Depends, File, Response, Streamed, Upload
from app.middlewares import authenticate
from app.models import User
from app.services import FilesService
from app.utils.bases import BaseController

type Actor = Annotated[User, Depends(authenticate)]
type Sent = Annotated[Upload, File()]

class FilesController(BaseController):

    def __init__ ( self, service: FilesService ) -> None:

        self._service = service

    async def store ( self, file: Sent, user: Actor ) -> Response:
        return self.created(await self._service.publish(file, user))

    async def keep ( self, file: Sent, user: Actor ) -> Response:
        return self.created(await self._service.keep(file, user))

    async def show ( self, path: str, user: Actor ) -> Streamed:

        chunks, mime = await self._service.open(path, user)

        return Response.stream(chunks, mime, path.rsplit("/", 1)[-1])
