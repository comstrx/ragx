from collections.abc import Mapping
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape
from core.date import date
from core.exceptions import Code, Fault
from core.number import number
from core.string import string

class View:

    def __init__ ( self ) -> None:

        self._env: Environment | None = None
        self._folder: Path | None = None

    def setup ( self, folder: Path, shared: Mapping[str, object] | None = None ) -> None:

        env = Environment(
            loader=FileSystemLoader(str(folder)), autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined, enable_async=True, trim_blocks=True, lstrip_blocks=True,
        )

        env.filters.update({
            "slug": string.slug, "truncate_text": string.truncate, "title_case": string.title,
            "iso": date.iso, "human": number.human, "percent": number.percent,
        })
        env.globals.update(dict(shared or {}))

        self._env    = env
        self._folder = folder

    def ready ( self ) -> bool:
        return self._env is not None

    def folder ( self ) -> Path:

        if self._folder is None: raise Fault(Code.INTERNAL, reason="view")

        return self._folder

    def exists ( self, name: str ) -> bool:

        if self._env is None: return False

        try: self._env.get_template(name)
        except TemplateNotFound: return False

        return True

    async def render ( self, name: str, /, **data: object ) -> str:

        if self._env is None: raise Fault(Code.INTERNAL, reason="view")

        try: template = self._env.get_template(name)
        except TemplateNotFound as error: raise Fault(Code.INTERNAL, reason=f"view.{name}") from error

        return await template.render_async(**data)

    async def text ( self, source: str, /, **data: object ) -> str:

        if self._env is None: raise Fault(Code.INTERNAL, reason="view")

        return await self._env.from_string(source).render_async(**data)
