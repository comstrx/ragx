from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from core.http import App
from bootstrap import application
import os, pytest

ENVIRONMENT = {
    "APP_ENV"    : "testing",
    "LOG_LEVEL"  : "warning",
    "DB_DATABASE": "ragx_test",
    "DB_PASSWORD": "ragx",
    "DB_SSLMODE" : "disable",
    "DB_MIGRATE" : "true",
    "DB_SEED"    : "true",
}


for name, value in ENVIRONMENT.items(): os.environ.setdefault(name, value)


@pytest.fixture(scope="session")
def anyio_backend () -> str:
    return "asyncio"


@pytest.fixture(scope="session")
async def app () -> AsyncIterator[App]:

    built = application()

    async with built.router.lifespan_context(built): yield built


@pytest.fixture
async def client ( app: App ) -> AsyncIterator[AsyncClient]:

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api") as client:
        yield client
