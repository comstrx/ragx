from collections.abc import Mapping, Sequence
from typing import Any, Self

from fastapi import Request
from enum import Enum

from pydantic import BaseModel
from core.date import date
from core.error import Code, Fault
from core.json import json
from core.parse import parse
from core.validate import validate
from .wire import JSON, Wire

FORMS = ("application/x-www-form-urlencoded", "multipart/form-data")
EMPTY : tuple[object, ...] = (None, "", [], {})

class Payload(Wire):

    def __init__ ( self, request: Request, body: Any = None, form: Mapping[str, Any] | None = None ) -> None:

        super().__init__(request)

        self._body    = body
        self._form    = dict(form or {})

    @classmethod
    async def of ( cls, request: Request ) -> Self:

        known = getattr(request.state, "payload", None)

        if isinstance(known, cls): return known

        built = cls(request, *await cls.read(request))

        request.state.payload = built

        return built

    @staticmethod
    async def read ( request: Request ) -> tuple[Any, Mapping[str, Any] | None]:

        kind = request.headers.get("content-type", "").split(";")[0].strip().lower()

        if request.method in ("GET", "HEAD", "OPTIONS"): return None, None
        if kind == JSON:

            raw = await request.body()

            if not raw: return None, None

            try: return json.loads(raw), None
            except ValueError as error: raise Fault(Code.BAD_REQUEST, reason="json") from error

        if kind in FORMS: return None, dict((await request.form()).multi_items())

        return None, None

    def body ( self ) -> Any:

        return self._body

    def form ( self, key: str | None = None, default: object = None ) -> Any:

        return self._form.get(key, default) if key else dict(self._form)

    def params ( self ) -> dict[str, Any]:

        return dict(self._request.path_params)

    def queries ( self ) -> dict[str, Any]:

        items: dict[str, Any] = {}

        for key, value in self._request.query_params.multi_items():

            if key.endswith("[]"): items.setdefault(key[:-2], []).append(value)
            else: items[key] = value

        return items

    def all ( self ) -> dict[str, Any]:

        body = self._body if isinstance(self._body, Mapping) else {}

        return { **self.queries(), **self._form, **body, **self.params() }

    def input ( self, key: str, default: object = None ) -> Any:

        return json.dig(self.all(), key, default)

    def query ( self, key: str, default: object = None ) -> Any:

        return self.queries().get(key, default)

    def param ( self, key: str, default: object = None ) -> Any:

        return self._request.path_params.get(key, default)

    def only ( self, *keys: str ) -> dict[str, Any]:

        data = self.all()

        return { key: data[key] for key in keys if key in data }

    def except_ ( self, *keys: str ) -> dict[str, Any]:

        return { key: value for key, value in self.all().items() if key not in keys }

    def has ( self, *keys: str ) -> bool:

        data = self.all()

        return all(key in data for key in keys)

    def has_any ( self, *keys: str ) -> bool:

        data = self.all()

        return any(key in data for key in keys)

    def filled ( self, *keys: str ) -> bool:

        data = self.all()

        return all(data.get(key) not in EMPTY for key in keys)

    def missing ( self, key: str ) -> bool:

        return key not in self.all()

    def boolean ( self, key: str, default: bool = False ) -> bool:

        return parse.bool(self.input(key, default))

    def integer ( self, key: str, default: int = 0 ) -> int:

        return parse.integer(self.input(key), default)

    def number ( self, key: str, default: float = 0.0 ) -> float:

        return parse.float(self.input(key), default)

    def text ( self, key: str, default: str = "" ) -> str:

        value = self.input(key)

        return default if value is None else str(value).strip()

    def items ( self, key: str ) -> list[Any]:

        return parse.list(self.input(key))

    def mapping ( self, key: str ) -> dict[str, Any]:

        return parse.dict(self.input(key))

    def date ( self, key: str, default: Any = None ) -> Any:

        value = self.input(key)

        if value in (None, ""): return default

        try: return date.parse(str(value))
        except Fault as error: raise Fault(Code.VALIDATION, errors={ key: ["Must be a valid date"] }) from error

    def enum[E: Enum] ( self, key: str, kind: type[E], default: E | None = None ) -> E | None:

        value = self.input(key)

        if value in (None, ""): return default

        try: return kind(value)
        except ValueError as error:

            choices = ", ".join(str(item.value) for item in kind)

            raise Fault(Code.VALIDATION, errors={ key: [f"Must be one of: {choices}"] }) from error

    def file ( self, key: str ) -> Any:

        found = self._form.get(key)

        return found if found is not None and hasattr(found, "filename") else None

    def has_file ( self, key: str ) -> bool:

        return self.file(key) is not None

    def merge ( self, **values: Any ) -> Payload:

        body = dict(self._body) if isinstance(self._body, Mapping) else {}

        return Payload(self._request, { **body, **values }, self._form)

    def when_has ( self, key: str, then: Any, otherwise: Any = None ) -> Any:

        return then(self.input(key)) if self.has(key) else (otherwise(self) if callable(otherwise) else otherwise)

    def when_filled ( self, key: str, then: Any, otherwise: Any = None ) -> Any:

        return then(self.input(key)) if self.filled(key) else (otherwise(self) if callable(otherwise) else otherwise)

    def validate[M: BaseModel] ( self, model: type[M] ) -> M:

        return validate.model(model, self.all())

    def shape ( self, **fields: Any ) -> dict[str, Any]:

        return validate.shape(self.all(), **fields)

    def require ( self, *names: str ) -> dict[str, Any]:

        validate.required(self.all(), *names)

        return self.only(*names)

    def one_of ( self, key: str, choices: Sequence[Any], default: Any = None ) -> Any:

        value = self.input(key, default)

        return validate.one_of(value, choices, key)

    def describe ( self ) -> dict[str, Any]:

        return {
            "method": self.method(), "path": self.path(), "route": self.route_name(), "json": self.is_json(),
            "keys": sorted(self.all()), "ip": self.ip(),
        }
