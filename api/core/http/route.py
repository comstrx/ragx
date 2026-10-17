from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Self

type Handler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Route:

    method  : str
    path    : str
    handler : Handler
    name    : str | None = None
    tags    : tuple[str, ...] = ()

    @classmethod
    def get ( cls, path: str, handler: Handler, name: str | None = None, tags: tuple[str, ...] = () ) -> Self:
        return cls("GET", path, handler, name, tags)

    @classmethod
    def post ( cls, path: str, handler: Handler, name: str | None = None, tags: tuple[str, ...] = () ) -> Self:
        return cls("POST", path, handler, name, tags)

    @classmethod
    def put ( cls, path: str, handler: Handler, name: str | None = None, tags: tuple[str, ...] = () ) -> Self:
        return cls("PUT", path, handler, name, tags)

    @classmethod
    def patch ( cls, path: str, handler: Handler, name: str | None = None, tags: tuple[str, ...] = () ) -> Self:
        return cls("PATCH", path, handler, name, tags)

    @classmethod
    def delete ( cls, path: str, handler: Handler, name: str | None = None, tags: tuple[str, ...] = () ) -> Self:
        return cls("DELETE", path, handler, name, tags)

    @staticmethod
    def group ( prefix: str, routes: Sequence[Route | Group], tags: tuple[str, ...] = () ) -> Group:
        return Group(prefix, tuple(routes), tags)


@dataclass(frozen=True, slots=True)
class Group:

    prefix : str
    routes : tuple[Route | Group, ...]
    tags   : tuple[str, ...] = ()

    def walk ( self, prefix: str = "", tags: tuple[str, ...] = () ) -> Iterator[tuple[str, tuple[str, ...], Route]]:

        base  = prefix + self.prefix
        owned = tags + self.tags

        for route in self.routes:

            if isinstance(route, Group): yield from route.walk(base, owned)
            else: yield base + route.path, owned + route.tags, route
