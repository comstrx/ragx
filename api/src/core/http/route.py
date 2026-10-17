from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Self

type Handler = Callable[..., Awaitable[Any]]
type Guard = Callable[..., Any]

CONVERTERS = ("int", "float", "uuid", "path", "str")
ACTIONS    = (
    ("index", "GET", ""), ("store", "POST", ""), ("show", "GET", "/{key}"),
    ("update", "PUT", "/{key}"), ("destroy", "DELETE", "/{key}"),
)

@dataclass(frozen=True, slots=True)
class Bound:

    path       : str
    methods    : tuple[str, ...]
    handler    : Handler
    name       : str | None
    tags       : tuple[str, ...]
    middleware : tuple[Guard, ...]
    throttle   : str | None

@dataclass(frozen=True, slots=True)
class Route:

    methods    : tuple[str, ...]
    path       : str
    handler    : Handler
    name       : str | None = None
    tags       : tuple[str, ...] = ()
    middleware : tuple[Guard, ...] = ()
    throttle   : str | None = None
    where      : Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def match (
        cls, methods: Sequence[str], path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = (),
    ) -> Self:
        return cls(tuple(method.upper() for method in methods), path, handler, name, tuple(tags))

    @classmethod
    def get ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:
        return cls.match(("GET",), path, handler, name, tags)

    @classmethod
    def post ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:
        return cls.match(("POST",), path, handler, name, tags)

    @classmethod
    def put ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:
        return cls.match(("PUT",), path, handler, name, tags)

    @classmethod
    def patch ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:
        return cls.match(("PATCH",), path, handler, name, tags)

    @classmethod
    def delete ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:
        return cls.match(("DELETE",), path, handler, name, tags)

    @classmethod
    def any ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:
        return cls.match(("GET", "POST", "PUT", "PATCH", "DELETE"), path, handler, name, tags)

    @staticmethod
    def group (
        prefix: str, routes: Sequence[Route | Group], tags: Sequence[str] = (), middleware: Sequence[Guard] = (),
        throttle: str | None = None, name: str | None = None,
    ) -> Group:
        return Group(prefix, tuple(routes), tuple(tags), tuple(middleware), throttle, name)

    @staticmethod
    def resource ( prefix: str, controller: object, only: Sequence[str] = (), name: str | None = None ) -> Group:

        wanted = set(only) if only else { action for action, _, _ in ACTIONS }
        routes = [
            Route.match((method,), path, getattr(controller, action), name=action)
            for action, method, path in ACTIONS
            if action in wanted and callable(getattr(controller, action, None))
        ]

        return Group(prefix, tuple(routes), (), (), None, name or prefix.strip("/").replace("/", "."))

    def guarded ( self, *guards: Guard ) -> Self:
        return replace(self, middleware=(*self.middleware, *guards))

    def limited ( self, rate: str ) -> Self:
        return replace(self, throttle=rate)

    def named ( self, name: str ) -> Self:
        return replace(self, name=name)

    def constrained ( self, **patterns: str ) -> Self:

        for parameter, kind in patterns.items():

            unknown = f"{parameter}:{kind}"

            if kind not in CONVERTERS: raise ValueError(unknown)

        return replace(self, where={ **self.where, **patterns })

    def pattern ( self, prefix: str ) -> str:

        path = prefix + self.path

        for parameter, kind in self.where.items(): path = path.replace(f"{{{parameter}}}", f"{{{parameter}:{kind}}}")

        return path

@dataclass(frozen=True, slots=True)
class Group:

    prefix     : str
    routes     : tuple[Route | Group, ...]
    tags       : tuple[str, ...] = ()
    middleware : tuple[Guard, ...] = ()
    throttle   : str | None = None
    name       : str | None = None

    def walk (
        self, prefix: str = "", tags: tuple[str, ...] = (), middleware: tuple[Guard, ...] = (),
        throttle: str | None = None, name: str = "",
    ) -> Iterator[Bound]:

        base   = prefix + self.prefix
        owned  = tags + self.tags
        guards = middleware + self.middleware
        rate   = self.throttle or throttle
        label  = f"{name}{self.name}." if self.name else name

        for route in self.routes:

            if isinstance(route, Group):

                yield from route.walk(base, owned, guards, rate, label)

                continue

            yield Bound(
                route.pattern(base), route.methods, route.handler,
                f"{label}{route.name}" if route.name else None,
                owned + route.tags, guards + route.middleware, route.throttle or rate,
            )

    def names ( self ) -> list[str]:
        return [bound.name for bound in self.walk() if bound.name]
