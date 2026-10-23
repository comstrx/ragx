from collections.abc import Awaitable, Callable, Sequence
from inspect import Parameter, Signature, isawaitable, isclass, isfunction, ismethod, signature
from types import NoneType, UnionType
from typing import Annotated, Any, TypeAliasType, Union, get_args, get_origin, get_type_hints

from engine.validate import Shape
from fastapi import Depends, File, Query, UploadFile
from starlette.requests import Request as Raw
from .request import Request, requested
from .wire import Inject, Upload

type Convert = Callable[[Any], Awaitable[Any]]

QUERIED = frozenset({"GET", "HEAD", "DELETE", "OPTIONS"})

def unwrap ( hint: Any ) -> Any:

    while isinstance(hint, TypeAliasType): hint = hint.__value__

    return hint

def split ( hint: Any ) -> tuple[Any, tuple[Any, ...]]:

    found = unwrap(hint)

    if get_origin(found) is not Annotated: return found, ()

    base, *meta = get_args(found)

    return unwrap(base), tuple(meta)

def nullable ( hint: Any ) -> tuple[Any, bool]:

    if get_origin(hint) not in (Union, UnionType): return hint, False

    kept = [arg for arg in get_args(hint) if arg is not NoneType]

    return (kept[0], True) if len(kept) == 1 else (hint, False)

async def uploaded ( file: UploadFile | None ) -> Upload | None:

    return Upload(file) if file is not None else None

class Endpoint:

    def __init__ (
        self, fn: Callable[..., Any], params: Sequence[Parameter], back: Any, converts: dict[str, Convert],
    ) -> None:

        self._fn           = fn
        self._converts     = converts
        self.__signature__ = Signature(params, return_annotation=back)
        self.__name__      = str(getattr(fn, "__name__", type(fn).__name__))
        self.__qualname__  = str(getattr(fn, "__qualname__", self.__name__))
        self.__doc__       = getattr(fn, "__doc__", None)

    async def __call__ ( self, **values: Any ) -> Any:

        for name, convert in self._converts.items(): values[name] = await convert(values[name])

        result = self._fn(**values)

        return await result if isawaitable(result) else result

class Binder:

    def __init__ ( self ) -> None:

        self._made: dict[tuple[Callable[..., Any], bool], Endpoint] = {}

    def bind ( self, fn: Callable[..., Any], methods: Sequence[str] = ("GET",) ) -> Endpoint:

        queried = all(method.upper() in QUERIED for method in methods)
        found   = self._made.get((fn, queried))

        if found is None: found = self._made[(fn, queried)] = self.build(fn, queried)

        return found

    def hints ( self, fn: Callable[..., Any] ) -> dict[str, Any]:

        target = fn if isfunction(fn) or ismethod(fn) else type(fn).__call__

        return get_type_hints(target, include_extras=True)

    def build ( self, fn: Callable[..., Any], queried: bool ) -> Endpoint:

        hints    = self.hints(fn)
        converts : dict[str, Convert] = {}
        params   : list[Parameter] = []

        for param in signature(fn).parameters.values():

            shaped, convert = self.shape(hints.get(param.name, param.annotation), queried)

            if convert is not None: converts[param.name] = convert

            params.append(param.replace(annotation=shaped, kind=Parameter.KEYWORD_ONLY))

        return Endpoint(fn, params, hints.get("return", Signature.empty), converts)

    def shape ( self, hint: Any, queried: bool ) -> tuple[Any, Convert | None]:

        base, meta     = split(hint)
        inner, absent  = nullable(base)
        injected       = next((item for item in meta if isinstance(item, Inject)), None)

        if injected is not None: return Annotated[base, Depends(self.bind(injected.using))], None
        if inner is Request: return Raw, requested
        if inner is Upload: return Annotated[UploadFile | None if absent else UploadFile, File()], uploaded
        if queried and not meta and isclass(inner) and issubclass(inner, Shape): return Annotated[base, Query()], None

        return hint, None
