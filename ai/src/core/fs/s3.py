from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from obstore.exceptions import BaseError
from obstore.store import S3Store
from core.error import Code, Fault
from .base import Pathish
from .driver import Driver, transfer
import obstore

FAILURES = (BaseError, FileNotFoundError)

@dataclass(frozen=True, slots=True)
class S3Options:

    region     : str = ""
    endpoint   : str = ""
    key        : str = ""
    secret     : str = ""
    prefix     : str = ""
    path_style : bool = False

    def store ( self, bucket: str ) -> S3Store:

        options: dict[str, Any] = { "virtual_hosted_style_request": not self.path_style }

        if self.region: options["region"] = self.region
        if self.endpoint: options["endpoint"] = self.endpoint
        if self.key: options["access_key_id"] = self.key
        if self.secret: options["secret_access_key"] = self.secret
        if self.prefix: options["prefix"] = self.prefix

        return S3Store(bucket, **options)

class S3Driver:

    def __init__ ( self, bucket: str, options: S3Options | None = None, url: str | None = None ) -> None:

        self._store = (options or S3Options()).store(bucket)
        self._url   = url.rstrip("/") if url else None

    def guard ( self, error: Exception, path: str | None = None ) -> Fault:

        if isinstance(error, FileNotFoundError): return Fault(Code.NOT_FOUND, reason=path)

        return Fault(Code.UNAVAILABLE, reason="storage.s3")

    async def put ( self, path: str, data: bytes, mime: str ) -> int:

        try: await obstore.put_async(self._store, path, data, attributes={ "Content-Type": mime })
        except FAILURES as error: raise self.guard(error) from error

        return len(data)

    async def get ( self, path: str ) -> bytes:

        try: return bytes(await (await obstore.get_async(self._store, path)).bytes_async())
        except FAILURES as error: raise self.guard(error, path) from error

    async def stream ( self, path: str ) -> AsyncIterator[bytes]:

        try: result = await obstore.get_async(self._store, path)
        except FAILURES as error: raise self.guard(error, path) from error

        return self._chunks_(result)

    async def _chunks_ ( self, result: Any ) -> AsyncIterator[bytes]:

        async for chunk in result.stream(): yield bytes(chunk)

    async def exists ( self, path: str ) -> bool:

        try: await obstore.head_async(self._store, path)
        except FileNotFoundError: return False
        except FAILURES as error: raise self.guard(error) from error

        return True

    async def modified ( self, path: str ) -> float:

        try: found = await obstore.head_async(self._store, path)
        except FAILURES as error: raise self.guard(error, path) from error

        stamp = found.get("last_modified")

        return float(stamp.timestamp()) if hasattr(stamp, "timestamp") else 0.0

    async def size ( self, path: str ) -> int:

        try: return int((await obstore.head_async(self._store, path))["size"])
        except FAILURES as error: raise self.guard(error, path) from error

    async def delete ( self, path: str ) -> bool:

        if not await self.exists(path): return False

        try: await obstore.delete_async(self._store, path)
        except FAILURES as error: raise self.guard(error) from error

        return True

    async def copy ( self, source: str, target: str ) -> None:

        try: await obstore.copy_async(self._store, source, target)
        except FAILURES as error: raise self.guard(error, source) from error

    async def move ( self, source: str, target: str ) -> None:

        try: await obstore.rename_async(self._store, source, target)
        except FAILURES as error: raise self.guard(error, source) from error

    async def list ( self, prefix: str = "" ) -> list[str]:

        try: found = await obstore.list(self._store, prefix or None).collect_async()
        except FAILURES as error: raise self.guard(error) from error

        return sorted(str(entry["path"]) for entry in found)

    def url ( self, path: str ) -> str | None:

        return f"{self._url}/{path}" if self._url else None

    async def temporary_url ( self, path: str, seconds: int ) -> str | None:

        try: return await obstore.sign_async(self._store, "GET", path, timedelta(seconds=seconds))
        except FAILURES as error: raise self.guard(error) from error

    def local ( self, _path: str ) -> Path | None:

        return None

    async def upload ( self, source: Pathish, path: str, mime: str | None = None ) -> int:

        return await transfer.upload(self, source, path, mime)

    async def download ( self, path: str, target: Pathish ) -> int:

        return await transfer.download(self, path, target)

    async def remove ( self, path: str ) -> bool:

        return await self.delete(path)

    async def sync ( self, other: Driver, prefix: str = "" ) -> int:

        return await transfer.sync(self, other, prefix)
