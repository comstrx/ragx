from typing import Annotated

from core.http import Query, Response
from app.requests import HelloRequest
from app.services import HelloService
from app.utils.bases import BaseController

class HelloController(BaseController):

    def __init__ ( self, service: HelloService ) -> None:

        self._service = service

    async def index ( self, query: Annotated[HelloRequest, Query()] ) -> Response:
        return self.ok(await self._service.greet(query.name))
