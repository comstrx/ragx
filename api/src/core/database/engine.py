from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any

from core.context import Work, context
from core.error import Code, Fault
from core.log import log
from sqlalchemy import event, text
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import QueuePool
from .session import FAILURES, SETTING, Adapter, Params, Row, Session, Statement, checkout, translate
import asyncio

RECYCLE   = 900
IDLE      = 5.0
RETRYABLE = frozenset({"database.serialization", "database.deadlock"})

class Database:

    def __init__ ( self ) -> None:

        self._engine: AsyncEngine | None = None
        self._reader: AsyncEngine | None = None
        self._adapter: Adapter | None = None
        self._current: ContextVar[Session | None] = ContextVar("transaction", default=None)
        self._bound: ContextVar[Mapping[str, str]] = ContextVar("bound", default=frozendict())
        self._follows: dict[str, str] = {}

    def ready ( self ) -> bool:

        return self._engine is not None

    def adapter ( self ) -> Adapter:

        if self._adapter is None: raise Fault(Code.UNAVAILABLE, reason="database")

        return self._adapter

    def dialect ( self ) -> Dialect:

        if self._engine is None: raise Fault(Code.UNAVAILABLE, reason="database")

        return self._engine.dialect

    async def connect (
        self, adapter: Adapter, url: str, min_size: int = 1, max_size: int = 10, wait: float = 5.0,
        options: Mapping[str, Any] | None = None, idle: float = IDLE,
    ) -> None:

        if self._engine is not None: return

        try:

            engine = create_async_engine(
                url, pool_size=max(max_size, min_size, 1), max_overflow=0, pool_timeout=wait, pool_use_lifo=True,
                pool_recycle=RECYCLE, connect_args=dict(options or {}),
            )

            async with asyncio.timeout(wait), engine.connect() as connection: await connection.execute(text("SELECT 1"))

        except FAILURES as error: raise translate.fault(error) from error

        event.listen(engine.sync_engine.pool, "checkout", checkout(engine.dialect, idle))

        self._engine  = engine
        self._reader  = engine.execution_options(isolation_level="AUTOCOMMIT")
        self._adapter = adapter

        log.info("database.connected", driver=adapter.name, min=min_size, max=max_size)

    async def close ( self ) -> None:

        if self._engine is None: return

        engine, self._engine, self._reader = self._engine, None, None

        await engine.dispose()
        log.info("database.closed")

    async def fill ( self, count: int ) -> int:

        if self._engine is None or count < 1: return 0

        barrier = asyncio.Barrier(count)

        async def hold () -> None:

            async with self._open_(self._engine) as connection:

                await connection.execute(text("SELECT 1"))
                await barrier.wait()

        await asyncio.gather(*(hold() for _ in range(count)))

        return count

    async def ping ( self, wait: float = 2.0 ) -> bool:

        if self._engine is None: return False

        try:

            async with asyncio.timeout(wait), self._engine.connect() as connection:
                return (await connection.execute(text("SELECT 1"))).scalar() == 1

        except FAILURES:

            log.warning("database.unreachable")

            return False

    def current ( self ) -> Session | None:

        return self._current.get()

    @contextmanager
    def bound ( self, settings: Mapping[str, str] ) -> Iterator[Mapping[str, str]]:

        if self._current.get() is not None: raise Fault(Code.INTERNAL, reason="database.bound.open")
        if not all(SETTING.fullmatch(name) for name in settings): raise Fault(Code.INTERNAL, reason="database.bound")

        merged = { **self._bound.get(), **settings }
        token  = self._bound.set(merged)

        try: yield merged
        finally: self._bound.reset(token)

    def follow ( self, setting: str, slot: str | None ) -> None:

        if not SETTING.fullmatch(setting): raise Fault(Code.INTERNAL, reason="database.bound")
        if slot is None: self._follows.pop(setting, None)
        else: self._follows[setting] = slot

    def settings ( self ) -> dict[str, str]:

        carried = { setting: str(context.get(slot)) for setting, slot in self._follows.items() if context.has(slot) }

        return { **carried, **self._bound.get() }

    def in_transaction ( self ) -> bool:

        return self._current.get() is not None

    def level ( self ) -> int:

        return 0 if (found := self._current.get()) is None else found.depth() + 1

    @asynccontextmanager
    async def session ( self ) -> AsyncGenerator[Session]:

        found = self._current.get()

        if found is not None:

            yield found

            return

        settings = self.settings()

        if not settings:

            async with self._open_(self._reader) as connection: yield Session(connection, self.adapter())

            return

        async with self._open_(self._engine) as connection, connection.begin():

            reader = Session(connection, self.adapter())

            await reader.bind(settings)

            yield reader

    @asynccontextmanager
    async def transaction ( self ) -> AsyncGenerator[Session]:

        found = self._current.get()

        if found is not None:

            async with self._nested_(found) as inner: yield inner

            return

        async with self._open_(self._engine) as connection:

            later = context.deferred.open()
            outer = Session(connection, self.adapter())
            token = self._current.set(outer)

            try:

                async with connection.begin():

                    await outer.bind(self.settings())

                    yield outer

            except BaseException:

                self._current.reset(token)
                context.deferred.drop(later)

                raise

            self._current.reset(token)

        await self._settle_(await context.deferred.flush(later))

    async def atomic[T] ( self, work: Callable[[], Awaitable[T]], attempts: int = 1 ) -> T:

        for attempt in range(1, max(attempts, 1) + 1):

            try:
                async with self.transaction(): return await work()
            except Fault as fault:

                if attempt >= attempts or fault.reason not in RETRYABLE or self.in_transaction(): raise

                log.warning("database.retried", attempt=attempt, reason=fault.reason)

        raise Fault(Code.INTERNAL, reason="database.atomic")

    async def after_commit ( self, work: Work ) -> bool:

        return await context.defer(work)

    async def fetch ( self, statement: Statement, params: Params = None ) -> list[Row]:

        async with self.session() as session: return await session.fetch(statement, params)

    async def row ( self, statement: Statement, params: Params = None ) -> Row | None:

        async with self.session() as session: return await session.row(statement, params)

    async def value ( self, statement: Statement, params: Params = None ) -> Any:

        async with self.session() as session: return await session.value(statement, params)

    async def execute ( self, statement: Statement, params: Params = None ) -> int:

        async with self.session() as session: return await session.execute(statement, params)

    def describe ( self ) -> Mapping[str, object]:

        if self._engine is None: return { "ready": False }

        pool = self._engine.pool

        if not isinstance(pool, QueuePool): return { "ready": True, "driver": self.adapter().name }

        return {
            "ready": True, "driver": self.adapter().name, "size": pool.size(), "idle": pool.checkedin(),
            "busy": pool.checkedout(), "overflow": pool.overflow(), "follows": dict(self._follows),
        }

    @asynccontextmanager
    async def _nested_ ( self, outer: Session ) -> AsyncGenerator[Session]:

        later = context.deferred.open()
        inner = outer.deeper()
        token = self._current.set(inner)

        try:

            async with outer.connection().begin_nested(): yield inner

        except BaseException as error:

            self._current.reset(token)
            context.deferred.drop(later)

            if isinstance(error, FAILURES): raise translate.fault(error) from error

            raise

        self._current.reset(token)
        context.deferred.merge(later)

    async def _settle_ ( self, failures: list[BaseException] ) -> None:

        for failure in failures: log.error("database.after_commit_failed", kind=type(failure).__name__)

        if failures: raise Fault.of(failures[0], Code.UNAVAILABLE, "database.after_commit")

    @asynccontextmanager
    async def _open_ ( self, engine: AsyncEngine | None ) -> AsyncGenerator[AsyncConnection]:

        if engine is None: raise Fault(Code.UNAVAILABLE, reason="database")

        try:

            async with engine.connect() as connection: yield connection

        except Fault: raise
        except FAILURES as error: raise translate.fault(error) from error
