from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape
from core.error import Code, Fault
from .filters import Filters

class View:

    def __init__ ( self ) -> None:

        self._env: Environment | None = None
        self._folder: Path | None = None
        self._filters = Filters()

    def setup ( self, folder: Path, shared: Mapping[str, object] | None = None, cache: int = 400 ) -> None:

        env = Environment(
            loader=FileSystemLoader(str(folder)), autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined, enable_async=True, trim_blocks=True, lstrip_blocks=True, cache_size=cache,
        )

        env.filters.update(self._filters.all())
        env.globals.update(self._filters.globals())
        env.globals.update(dict(shared or {}))

        self._env    = env
        self._folder = folder

    def ready ( self ) -> bool:
        return self._env is not None

    def engine ( self ) -> Environment:

        if self._env is None: raise Fault(Code.INTERNAL, reason="view")

        return self._env

    def folder ( self ) -> Path:

        if self._folder is None: raise Fault(Code.INTERNAL, reason="view")

        return self._folder

    def share ( self, **values: object ) -> None:
        self.engine().globals.update(values)

    def filter ( self, name: str, fn: Callable[..., Any] ) -> None:
        self.engine().filters[name] = fn

    def exists ( self, name: str ) -> bool:

        if self._env is None: return False

        try: self._env.get_template(name)
        except TemplateNotFound: return False

        return True

    def names ( self ) -> list[str]:
        return self.engine().list_templates()

    async def render ( self, name: str, /, **data: object ) -> str:

        try: template = self.engine().get_template(name)
        except TemplateNotFound as error: raise Fault(Code.INTERNAL, reason=f"view.{name}") from error

        return await template.render_async(**data)

    async def first ( self, names: list[str], /, **data: object ) -> str:

        for name in names:
            if self.exists(name): return await self.render(name, **data)

        raise Fault(Code.INTERNAL, reason=f"view.{names[0] if names else 'none'}")

    async def text ( self, source: str, /, **data: object ) -> str:
        return await self.engine().from_string(source).render_async(**data)

    def describe ( self ) -> dict[str, object]:
        return { "ready": self.ready(), "folder": str(self._folder) if self._folder else None }
