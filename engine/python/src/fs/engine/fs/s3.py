from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, ClassVar, override

from engine.error import Code, Fault
from obstore.exceptions import BaseError, PermissionDeniedError, UnauthenticatedError
from obstore.store import S3Store
from .driver import CORE, SIGN, Driver
import builtins, obstore

FAILURES = (BaseError, FileNotFoundError, ValueError)

@dataclass(frozen=True, slots=True)
class S3Options:

    region     : str = ""
    endpoint   : str = ""
    key        : str = ""
    secret     : str = ""
    prefix     : str = ""
    path_style : bool = False

def opened ( options: S3Options, bucket: str ) -> S3Store:

    settings: dict[str, Any] = { "virtual_hosted_style_request": not options.path_style }

    if options.region: settings["region"] = options.region
    if options.endpoint: settings["endpoint"] = options.endpoint
    if options.key: settings["access_key_id"] = options.key
    if options.secret: settings["secret_access_key"] = options.secret
    if options.prefix: settings["prefix"] = options.prefix

    plain = options.endpoint.startswith("http://")

    return S3Store(bucket, client_options={ "allow_http": plain }, **settings)

class S3Driver(Driver):

    name         = "s3"
    capabilities : ClassVar[frozenset[str]] = CORE | {SIGN}

    def __init__ ( self, bucket: str, options: S3Options | None = None, url: str | None = None ) -> None:

        super().__init__(url)

        self._store = opened(options or S3Options(), bucket)

    def guard ( self, error: Exception, action: str ) -> Fault:

        if isinstance(error, FileNotFoundError) and action == "put": return self.fault(Code.INTERNAL, "bucket")
        if isinstance(error, FileNotFoundError): return Fault(Code.NOT_FOUND, reason="fs.missing")
        if isinstance(error, ValueError): return Fault(Code.BAD_REQUEST, reason="fs.path")
        if isinstance(error, PermissionDeniedError | UnauthenticatedError): return self.fault(Code.INTERNAL, "denied")

        return self.fault(Code.UNAVAILABLE, action)

    @override
    async def put ( self, path: str, data: bytes, mime: str ) -> int:

        try: await obstore.put_async(self._store, path, data, attributes={ "Content-Type": mime })
        except FAILURES as error: raise self.guard(error, "put") from error

        return len(data)

    @override
    async def get ( self, path: str ) -> bytes:

        try: return bytes(await (await obstore.get_async(self._store, path)).bytes_async())
        except FAILURES as error: raise self.guard(error, "get") from error

    @override
    async def stream ( self, path: str ) -> AsyncIterator[bytes]:

        try: result = await obstore.get_async(self._store, path)
        except FAILURES as error: raise self.guard(error, "stream") from error

        return self._chunks_(result)

    async def _chunks_ ( self, result: Any ) -> AsyncIterator[bytes]:

        async for chunk in result.stream(): yield bytes(chunk)

    @override
    async def exists ( self, path: str ) -> bool:

        try: await obstore.head_async(self._store, path)
        except FileNotFoundError: return False
        except FAILURES as error: raise self.guard(error, "exists") from error

        return True

    @override
    async def modified ( self, path: str ) -> float:

        try: found = await obstore.head_async(self._store, path)
        except FAILURES as error: raise self.guard(error, "modified") from error

        return found["last_modified"].timestamp()

    @override
    async def size ( self, path: str ) -> int:

        try: return int((await obstore.head_async(self._store, path))["size"])
        except FAILURES as error: raise self.guard(error, "size") from error

    @override
    async def delete ( self, path: str ) -> bool:

        if not await self.exists(path): return False

        try: await obstore.delete_async(self._store, path)
        except FAILURES as error: raise self.guard(error, "delete") from error

        return True

    @override
    async def copy ( self, source: str, target: str ) -> None:

        try: await obstore.copy_async(self._store, source, target)
        except FAILURES as error: raise self.guard(error, "copy") from error

    @override
    async def move ( self, source: str, target: str ) -> None:

        try: await obstore.rename_async(self._store, source, target)
        except FAILURES as error: raise self.guard(error, "move") from error

    @override
    async def list ( self, prefix: str = "" ) -> builtins.list[str]:

        try: found = await obstore.list(self._store, prefix or None).collect_async()
        except FAILURES as error: raise self.guard(error, "list") from error

        return sorted(str(entry["path"]) for entry in found)

    @override
    async def temporary_url ( self, path: str, seconds: int ) -> str:

        try: return await obstore.sign_async(self._store, "GET", path, timedelta(seconds=seconds))
        except FAILURES as error: raise self.guard(error, "sign") from error
