from collections.abc import AsyncIterator

from engine.config import env
from engine.http import App
from engine.mail import LogMailer, mail
from engine.test import Client, expect, test
from bootstrap import application
import inspect, os, pytest

ENVIRONMENT = {
    "APP_ENV"           : "testing",
    "LOG_LEVEL"         : "warning",
    "DB_DATABASE"       : "ragx_test",
    "DB_PASSWORD"       : "ragx",
    "DB_SSLMODE"        : "disable",
    "DB_MIGRATE"        : "true",
    "DB_SEED"           : "true",
    "MAIL_DRIVER"       : "log",
    "AUTH_SECRET"       : "testing-secret-that-is-long-enough-for-hs256-0001",
    "AUTH_ISSUER"       : "ragx-test",
    "QUEUE_DRIVER"      : "memory",
    "QUEUE_QUEUES"      : '["default","maintenance"]',
    "QUEUE_WORKERS"     : "0",
    "SCHEDULE_ENABLED"  : "false",
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

    built = application()

    expect((env.text("APP_ENV"), env.text("DB_DATABASE"))).equals(("testing", ENVIRONMENT["DB_DATABASE"]))

    async with built.lifespan(): yield built

@pytest.fixture
async def client ( app: App ) -> AsyncIterator[Client]:

    async with test.client(app, "http://api") as client: yield client

@pytest.fixture
def outbox ( app: App ) -> LogMailer:

    found = mail.outbox()

    found.clear()

    return found
