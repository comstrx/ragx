from core.exceptions import Code, Fault
from core.http import Facts, Request, Response
from app.services import HealthService
from app.utils.bases import BaseController

class HealthController(BaseController):

    def __init__ ( self, service: HealthService ) -> None:

        self._service = service

    async def index ( self, request: Request ) -> Response:

        alive, report = await self._service.status(Facts.of(request))

        if not alive: return Response.fail(Fault(Code.UNAVAILABLE, reason="database"), meta={ "health": report })

        return self.ok(report)
