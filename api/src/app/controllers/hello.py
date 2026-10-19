from core.http import Response
from app.requests import HelloRequest
from app.services import HelloService
from app.utils.cycle import Controller

class HelloController(Controller):

    def __init__ ( self, service: HelloService ) -> None:

        self._service = service

    async def index ( self, query: HelloRequest ) -> Response:

        return self.ok(await self._service.greet(query.name))
