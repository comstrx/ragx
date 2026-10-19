from collections.abc import Awaitable, Callable
from typing import Any

import functools, importlib, inspect, pkgutil

type Fn[**P, T] = Callable[P, T]

class Call:

    def name ( self, fn: Callable[..., object] ) -> str:

        return f"{fn.__module__}.{getattr(fn, '__qualname__', type(fn).__name__)}"

    def short_name ( self, fn: Callable[..., object] ) -> str:

        return getattr(fn, "__qualname__", type(fn).__name__)

    def is_async ( self, fn: Callable[..., object] ) -> bool:

        return inspect.iscoroutinefunction(fn) or inspect.iscoroutinefunction(type(fn).__call__)

    def is_generator ( self, fn: Callable[..., object] ) -> bool:

        return inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn)

    def arguments ( self, fn: Callable[..., object] ) -> dict[str, object]:

        empty = inspect.Parameter.empty

        return {
            name: (None if parameter.default is empty else parameter.default)
            for name, parameter in inspect.signature(fn).parameters.items()
        }

    def required ( self, fn: Callable[..., object] ) -> list[str]:

        empty = inspect.Parameter.empty

        return [
            name for name, parameter in inspect.signature(fn).parameters.items()
            if parameter.default is empty and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]

    def accepts ( self, fn: Callable[..., object], name: str ) -> bool:

        parameters = inspect.signature(fn).parameters

        return name in parameters or any(p.kind is p.VAR_KEYWORD for p in parameters.values())

    def arity ( self, fn: Callable[..., object] ) -> int:

        return len(inspect.signature(fn).parameters)

    def returns ( self, fn: Callable[..., object] ) -> object:

        return inspect.signature(fn).return_annotation

    async def call ( self, fn: Callable[..., object], *args: object, **kwargs: object ) -> Any:

        result = fn(*args, **kwargs)

        return await result if inspect.isawaitable(result) else result

    async def call_with ( self, fn: Callable[..., object], **available: object ) -> Any:

        wanted = { name: value for name, value in available.items() if self.accepts(fn, name) }

        return await self.call(fn, **wanted)

    def pipe[T] ( self, *steps: Callable[[T], T] ) -> Callable[[T], T]:

        def run ( value: T ) -> T:

            for step in steps: value = step(value)

            return value

        return run

    def compose[T] ( self, *steps: Callable[[T], T] ) -> Callable[[T], T]:

        return self.pipe(*reversed(steps))

    def pipe_async[T] ( self, *steps: Callable[[T], Awaitable[T] | T] ) -> Callable[[T], Awaitable[T]]:

        async def run ( value: T ) -> T:

            for step in steps:

                result = step(value)
                value  = await result if inspect.isawaitable(result) else result

            return value

        return run

    def tap[T] ( self, value: T, fn: Callable[[T], object] ) -> T:

        fn(value)

        return value

    def identity[T] ( self, value: T ) -> T:

        return value

    def constant[T] ( self, value: T ) -> Callable[..., T]:

        return lambda *_, **__: value

    def noop ( self, *_: object, **__: object ) -> None:

        return None

    def partial[T] ( self, fn: Callable[..., T], *args: object, **kwargs: object ) -> Callable[..., T]:

        return functools.partial(fn, *args, **kwargs)

    def flip[A, B, T] ( self, fn: Callable[[A, B], T] ) -> Callable[[B, A], T]:

        return lambda b, a: fn(a, b)

    def negate ( self, test: Callable[..., bool] ) -> Callable[..., bool]:

        return lambda *args, **kwargs: not test(*args, **kwargs)

    def apply_each[T] ( self, fns: list[Callable[[T], object]], value: T ) -> list[object]:

        return [fn(value) for fn in fns]

    def load ( self, target: str ) -> Any:

        module, _, attribute = target.partition(":")
        loaded               = importlib.import_module(module)

        return getattr(loaded, attribute) if attribute else loaded

    def discover ( self, package: str, test: Callable[[Any], bool] | None = None ) -> list[Any]:

        root  = importlib.import_module(package)
        found: list[Any] = []

        for info in pkgutil.iter_modules(getattr(root, "__path__", [])):

            module = importlib.import_module(f"{package}.{info.name}")

            public = [(name, value) for name, value in vars(module).items() if not name.startswith("_")]

            found.extend(value for _, value in public if test is None or test(value))

        return found

    def juxt[T] ( self, *fns: Callable[[T], object] ) -> Callable[[T], list[object]]:

        return lambda value: [fn(value) for fn in fns]

    def unary[T, R] ( self, fn: Callable[..., R] ) -> Callable[[T], R]:

        def one ( value: T ) -> R:

            return fn(value)

        return one

    def after[T] ( self, times: int, fn: Callable[..., T] ) -> Callable[..., T | None]:

        calls = 0

        def gated ( *args: object, **kwargs: object ) -> T | None:

            nonlocal calls

            calls += 1

            return fn(*args, **kwargs) if calls >= times else None

        return gated

    def before[T] ( self, times: int, fn: Callable[..., T] ) -> Callable[..., T | None]:

        calls = 0
        last: list[T] = []

        def gated ( *args: object, **kwargs: object ) -> T | None:

            nonlocal calls

            calls += 1

            if calls < times: last[:] = [fn(*args, **kwargs)]

            return last[0] if last else None

        return gated

    def curry ( self, fn: Callable[..., Any], arity: int | None = None ) -> Callable[..., Any]:

        wanted = arity if arity is not None else self.arity(fn)

        def curried ( *args: object ) -> Any:

            if len(args) >= wanted: return fn(*args)

            return lambda *more: curried(*args, *more)

        return curried
