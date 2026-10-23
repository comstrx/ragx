from collections.abc import AsyncIterator

from engine.config import env
from engine.http import App
from engine.test import test
import inspect, os, pytest

ENVIRONMENT = {
    "LOG_LEVEL"   : "warning",
    "DB_DATABASE" : "engine_test",
    "DB_USERNAME" : "engine",
    "DB_PASSWORD" : "engine",
    "DB_SSLMODE"  : "disable",
}

for name, value in ENVIRONMENT.items(): os.environ.setdefault(name, value)

def pytest_collection_modifyitems ( items: list[pytest.Item] ) -> None:

    for item in items:

        coroutine = isinstance(item, pytest.Function) and inspect.iscoroutinefunction(item.obj)

        if coroutine: item.add_marker(pytest.mark.anyio)

@pytest.fixture(scope="session")
def anyio_backend () -> str:

    return "asyncio"

@pytest.fixture(scope="session")
async def app () -> AsyncIterator[App]:

    await test.provision()

    built = test.application()

    test.expect(env.text("DB_DATABASE")).equals(ENVIRONMENT["DB_DATABASE"])

    async with built.lifespan(): yield built
