from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, NoReturn

from starlette.testclient import TestClient
from engine.database import Provisioned
from engine.error import Code, Fault
from engine.http import App, Group, Route
from engine.log import log
from .client import Client, Sockets, Stub
from .expect import Expect, Mismatch, mismatch
from .stage import Relay, Stage
import asyncio, importlib, pkgutil, unittest

SIZED = (list, dict, set, frozenset, tuple)

def owned ( value: object ) -> bool:

    return type(value).__module__.startswith("engine.") and not isinstance(value, type)

def fields ( value: object ) -> list[str]:

    slots = [klass.__dict__.get("__slots__", ()) for klass in type(value).__mro__]
    named = [name for group in slots for name in ((group,) if isinstance(group, str) else group)]

    return [*getattr(value, "__dict__", {}), *named]

def weight ( item: object, depth: int = 2 ) -> int:

    if not isinstance(item, SIZED): return 0

    inner = list(item.values()) if isinstance(item, dict) else list(item)

    return len(item) + (sum(weight(part, depth - 1) for part in inner) if depth > 0 else 0)

def measured ( prefix: str, value: object, depth: int ) -> dict[str, int]:

    found: dict[str, int] = {}

    for name in fields(value):

        item = getattr(value, name, None)

        if isinstance(item, SIZED): found[f"{prefix}.{name}"] = weight(item)
        elif depth > 0 and owned(item): found.update(measured(f"{prefix}.{name}", item, depth - 1))

    return found

@dataclass(slots=True)
class Caught:

    fault: Fault | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def expect ( self ) -> Expect:

        return Expect(self.fault, "fault")

class Catch:

    __slots__ = ("_check", "_kinds", "_missing", "caught")

    def __init__ (
        self, kinds: tuple[type[BaseException], ...], check: Callable[[BaseException], None], missing: str,
    ) -> None:

        self._kinds   = kinds
        self._check   = check
        self._missing = missing
        self.caught   = Caught()

    def __enter__ ( self ) -> Caught:

        return self.caught

    def __exit__ ( self, kind: type[BaseException] | None, error: BaseException | None, trace: object ) -> bool:

        if error is None: mismatch(self._missing)
        if not isinstance(error, self._kinds): return False

        self._check(error)

        self.caught.fault = error if isinstance(error, Fault) else None

        return True

def verify ( fault: Fault, code: Code | None, reason: str | None, field_name: str | None ) -> None:

    if code is not None and fault.code is not code:
        mismatch(f"fault: expected code {code.value}, got {fault.code.value} ({fault.reason})")
    if reason is not None and fault.reason != reason:
        mismatch(f"fault: expected reason {reason!r}, got {fault.reason!r}")
    if field_name is not None and not (fault.errors and fault.errors.get(field_name)):
        mismatch(f"fault: expected errors on {field_name!r}, got {fault.errors!r}")

class Harness:

    def expect ( self, value: Any, label: str = "value" ) -> Expect:

        return Expect(value, label)

    def skip ( self, reason: str ) -> NoReturn:

        raise unittest.SkipTest(reason)

    def footprint ( self ) -> dict[str, int]:

        found: dict[str, int] = {}
        root = importlib.import_module("engine")

        for info in pkgutil.iter_modules(root.__path__):

            module = importlib.import_module(f"engine.{info.name}")

            for name, value in vars(module).items():

                if not name.startswith("_") and owned(value): found.update(measured(f"{info.name}.{name}", value, 2))

        current = asyncio.current_task()

        found["tasks"] = sum(1 for task in asyncio.all_tasks() if task is not current) if current else 0

        return found

    def some[T] ( self, value: T | None, label: str = "value" ) -> T:

        if value is None: mismatch(f"{label}: expected a value, got None")

        return value

    def kind[T] ( self, value: object, of: type[T], label: str = "value" ) -> T:

        if not isinstance(value, of): mismatch(f"{label}: expected {of.__name__}, got {type(value).__name__}")

        return value

    def client (
        self, app: App, base: str = "http://test", peer: tuple[str, int] = ("127.0.0.1", 50000),
        lifespan: bool = False, headers: dict[str, str] | None = None,
    ) -> Client:

        return Client(app, base, peer, lifespan, headers)

    @contextmanager
    def sockets ( self, app: App ) -> Iterator[Sockets]:

        with TestClient(app) as client: yield Sockets(client)

    def stub ( self ) -> Stub:

        return Stub()

    def fails ( self, code: Code | None = None, reason: str | None = None, field: str | None = None ) -> Catch:

        def check ( error: BaseException ) -> None:

            if isinstance(error, Fault): verify(error, code, reason, field)

        return Catch((Fault,), check, f"expected a fault {code.value if code else ''} {reason or ''}".rstrip())

    def raises ( self, kind: type[BaseException], text: str | None = None ) -> Catch:

        def check ( error: BaseException ) -> None:

            if text is not None and text not in str(error):
                mismatch(f"expected {kind.__name__} mentioning {text!r}, got {error!r}")

        return Catch((kind,), check, f"expected {kind.__name__} to be raised")

    async def rejects (
        self, work: Callable[[], Awaitable[Any]] | Awaitable[Any], code: Code | None = None,
        reason: str | None = None, field: str | None = None,
    ) -> Fault:

        try: await (work() if callable(work) else work)
        except Fault as fault:

            verify(fault, code, reason, field)

            return fault

        message = f"expected a fault {code.value if code else ''} {reason or ''}".rstrip()

        raise Mismatch(message)

    def application ( self, *routes: Route | Group, name: str = "engine" ) -> App:

        return Stage().application(*routes, name=name)

    async def provision ( self ) -> Provisioned:

        return await Stage().provision()

    @asynccontextmanager
    async def relay ( self, host: str, port: int ) -> AsyncIterator[Relay]:

        made = Relay(host, port)

        await made.up()

        try: yield made
        finally: await made.down()

    @contextmanager
    def logs ( self, *events: str ) -> Iterator[Caught]:

        caught = Caught()

        with log.capture() as captured:

            yield caught

            caught.events.extend(dict(event) for event in captured)

        names = [event.get("event") for event in caught.events]
        lost  = [event for event in events if event not in names]

        if lost: mismatch(f"expected log events {lost!r}, got {names!r}")

    @contextmanager
    def quiet ( self, *events: str ) -> Iterator[Caught]:

        caught = Caught()

        with log.capture() as captured:

            yield caught

            caught.events.extend(dict(event) for event in captured)

        found = [event.get("event") for event in caught.events if event.get("event") in events]

        if found: mismatch(f"expected no log events {found!r}")
