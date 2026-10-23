from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Self

from engine.error import Code, Fault
from .request import Request
from .response import Response
import re

type Handler = Callable[..., Awaitable[Any]]
type Guard = Callable[..., Any]

CONVERTERS = ("int", "float", "uuid", "path", "str")
PARAM      = re.compile(r"\{(\w+)\}")
ALL        = ("GET", "POST", "PUT", "PATCH", "DELETE")
ACTIONS    = (
    ("index", "GET", ""), ("store", "POST", ""), ("show", "GET", "/{key}"),
    ("update", "PUT", "/{key}"), ("patch", "PATCH", "/{key}"), ("destroy", "DELETE", "/{key}"),
)

def host_guard ( pattern: str ) -> Guard:

    escaped = re.escape(pattern).replace(r"\{", "{").replace(r"\}", "}")
    regex   = re.compile("^" + PARAM.sub(lambda found: f"(?P<{found.group(1)}>[^.]+)", escaped) + "$")

    async def domain ( request: Request ) -> None:

        found = regex.match(request.host())

        if found is None: raise Fault(Code.NOT_FOUND, reason="domain")

        request.assign(domain=found.groupdict())

    domain.__name__ = f"domain_{pattern.replace('.', '_')}"

    return domain

@dataclass(frozen=True, slots=True)
class Bound:

    path       : str
    methods    : tuple[str, ...]
    handler    : Handler
    name       : str | None
    tags       : tuple[str, ...]
    middleware : tuple[Guard, ...]
    throttle   : str | None
    hidden     : bool = False

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
    hidden     : bool = False

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
    def options ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:

        return cls.match(("OPTIONS",), path, handler, name, tags)

    @classmethod
    def head ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:

        return cls.match(("HEAD",), path, handler, name, tags)

    @classmethod
    def any ( cls, path: str, handler: Handler, name: str | None = None, tags: Sequence[str] = () ) -> Self:

        return cls.match(ALL, path, handler, name, tags)

    @classmethod
    def permanent_redirect ( cls, path: str, target: str, name: str | None = None ) -> Self:

        return cls.redirect(path, target, 308, name)

    @classmethod
    def fallback ( cls, handler: Handler, name: str = "fallback" ) -> Self:

        return cls.match(ALL, "/{fallback}", handler, name).constrained(fallback="path")

    @classmethod
    def redirect ( cls, path: str, target: str, status: int = 307, name: str | None = None ) -> Self:

        async def send () -> Response:

            return Response.redirect(target, status)

        return cls.match(("GET",), path, send, name)

    @staticmethod
    def group (
        prefix: str, routes: Sequence[Route | Group], tags: Sequence[str] = (), middleware: Sequence[Guard] = (),
        throttle: str | None = None, name: str | None = None, domain: str | None = None,
    ) -> Group:

        guards = (host_guard(domain), *middleware) if domain else tuple(middleware)

        return Group(prefix, tuple(routes), tuple(tags), guards, throttle, name)

    @staticmethod
    def resource (
        prefix: str, controller: object, only: Sequence[str] = (), except_: Sequence[str] = (), name: str | None = None,
    ) -> Group:

        wanted = (set(only) if only else { action for action, _, _ in ACTIONS }) - set(except_)
        routes = [
            Route.match((method,), path, getattr(controller, action), name=action)
            for action, method, path in ACTIONS
            if action in wanted and callable(getattr(controller, action, None))
        ]

        return Group(prefix, tuple(routes), (), (), None, name or prefix.strip("/").replace("/", "."))

    def guarded ( self, *guards: Guard ) -> Self:

        return replace(self, middleware=(*self.middleware, *guards))

    def tagged ( self, *tags: str ) -> Self:

        return replace(self, tags=(*self.tags, *tags))

    def domain ( self, pattern: str ) -> Self:

        return replace(self, middleware=(host_guard(pattern), *self.middleware))

    def limited ( self, rate: str ) -> Self:

        return replace(self, throttle=rate)

    def named ( self, name: str ) -> Self:

        return replace(self, name=name)

    def hide ( self ) -> Self:

        return replace(self, hidden=True)

    def constrained ( self, **patterns: str ) -> Self:

        for parameter, kind in patterns.items():

            unknown = f"{parameter}:{kind}"

            if kind not in CONVERTERS: raise Fault(Code.INTERNAL, reason=f"http.converter.{unknown}")

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
                owned + route.tags, guards + route.middleware, route.throttle or rate, route.hidden,
            )

    def names ( self ) -> list[str]:

        return [bound.name for bound in self.walk() if bound.name]

    def find ( self, name: str ) -> Bound | None:

        return next((bound for bound in self.walk() if bound.name == name), None)

    def paths ( self ) -> list[str]:

        return [bound.path for bound in self.walk()]
