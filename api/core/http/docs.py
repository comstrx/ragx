from fastapi import Request
from scalar_fastapi import get_scalar_api_reference
from starlette.responses import HTMLResponse


class Docs:

    @staticmethod
    async def scalar ( request: Request ) -> HTMLResponse:

        openapi_url = f"{request.scope.get('root_path', '')}{request.app.openapi_url}"

        return get_scalar_api_reference(openapi_url=openapi_url, title=request.app.title, telemetry=False)
