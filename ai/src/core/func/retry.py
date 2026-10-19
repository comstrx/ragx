from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from random import SystemRandom
from typing import TypedDict, Unpack, cast
import asyncio, functools, inspect, time

from core.error import Code, Fault

type Fn[**P, T] = Callable[P, T]
type Catch = tuple[type[BaseException], ...]
type When = Callable[[BaseException], bool]

JITTER = SystemRandom()

class Options(TypedDict, total=False):

    times      : int
    delay      : float
    backoff    : float
    cap        : float | None
    jitter     : bool
    idempotent : bool
    on         : Catch
    when       : When | None

@dataclass(frozen=True, slots=True)
class Policy:

    times      : int = 3
    delay      : float = 0.1
    backoff    : float = 2.0
    cap        : float | None = None
    jitter     : bool = False
    idempotent : bool = False
    on         : Catch = (Exception,)
    when       : When | None = None

    def waits ( self ) -> list[float]:

        if self.times < 1: raise Fault(Code.INTERNAL, reason="retry.times")

        found = [self.delay * (self.backoff ** step) for step in range(self.times - 1)]
        caped = [min(wait, self.cap) if self.cap is not None else wait for wait in found]

        return [JITTER.uniform(0, wait) for wait in caped] if self.jitter else caped

    def again ( self, error: BaseException ) -> bool:

        if not isinstance(error, self.on): return False
        if self.when is not None: return self.when(error)
        if isinstance(error, Fault): return error.safe(self.idempotent)
        if isinstance(error, TimeoutError): return self.idempotent

        return True

class Retry:

    def policy (
        self, times: int = 3, delay: float = 0.1, backoff: float = 2.0, cap: float | None = None, jitter: bool = False,
        idempotent: bool = False, on: Catch = (Exception,), when: When | None = None,
    ) -> Policy:

        return Policy(times, delay, backoff, cap, jitter, idempotent, on, when)

    def waits ( self, times: int, delay: float, backoff: float, cap: float | None = None ) -> list[float]:

        return Policy(times, delay, backoff, cap).waits()

    def retry[**P, T] ( self, fn: Fn[P, T], policy: Policy | None = None, **options: Unpack[Options] ) -> Fn[P, T]:

        chosen = policy or Policy(**options)
        waits = chosen.waits()

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def again_async ( *args: P.args, **kwargs: P.kwargs ) -> object:

                for wait in waits:

                    try: return await cast("Awaitable[object]", fn(*args, **kwargs))
                    except BaseException as error:

                        if not chosen.again(error): raise

                    await asyncio.sleep(wait)

                return await cast("Awaitable[object]", fn(*args, **kwargs))

            return cast("Fn[P, T]", again_async)

        @functools.wraps(fn)
        def again ( *args: P.args, **kwargs: P.kwargs ) -> T:

            for wait in waits:

                try: return fn(*args, **kwargs)
                except BaseException as error:

                    if not chosen.again(error): raise

                time.sleep(wait)

            return fn(*args, **kwargs)

        return again

    def timeout[**P, T] (
        self, fn: Fn[P, Awaitable[T]], seconds: float, reason: str = "timeout",
    ) -> Fn[P, Awaitable[T]]:

        if not inspect.iscoroutinefunction(fn): raise Fault(Code.INTERNAL, reason="timeout.sync")

        @functools.wraps(fn)
        async def bounded ( *args: P.args, **kwargs: P.kwargs ) -> T:

            try:
                async with asyncio.timeout(seconds): return await fn(*args, **kwargs)
            except TimeoutError as error: raise Fault(Code.UNAVAILABLE, reason=reason, unknown=True) from error

        return bounded

    def until[T] (
        self, fn: Callable[[], T], done: Callable[[T], bool], times: int = 10, delay: float = 0.1, backoff: float = 1.0,
    ) -> T:

        result = fn()

        for wait in self.waits(times, delay, backoff):

            if done(result): return result

            time.sleep(wait)

            result = fn()

        return result

    async def until_async[T] (
        self, fn: Callable[[], Awaitable[T]], done: Callable[[T], bool],
        times: int = 10, delay: float = 0.1, backoff: float = 1.0,
    ) -> T:

        result = await fn()

        for wait in self.waits(times, delay, backoff):

            if done(result): return result

            await asyncio.sleep(wait)

            result = await fn()

        return result
