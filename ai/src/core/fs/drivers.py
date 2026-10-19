from pathlib import Path

from core.error import Code, Fault
from .base import Pathish
from .driver import Driver, transfer
from .local import LocalDriver
from .s3 import S3Driver, S3Options

class Drivers:

    def __init__ ( self ) -> None:

        self._known: dict[str, Driver] = {}

    def register ( self, name: str, driver: Driver ) -> Driver:

        self._known[name] = driver

        return driver

    def use ( self, name: str ) -> Driver:

        found = self._known.get(name)

        if found is None: raise Fault(Code.INTERNAL, reason=f"fs.driver.{name}")

        return found

    def has ( self, name: str ) -> bool:

        return name in self._known

    def names ( self ) -> list[str]:

        return sorted(self._known)

    def forget ( self, name: str ) -> bool:

        return self._known.pop(name, None) is not None

    async def sync ( self, source: str, target: str, prefix: str = "" ) -> int:

        return await transfer.sync(self.use(source), self.use(target), prefix)

    def local ( self, name: str, root: Pathish, url: str | None = None ) -> LocalDriver:

        driver = LocalDriver(Path(root), url)

        self.register(name, driver)

        return driver

    def s3 ( self, name: str, bucket: str, options: S3Options | None = None, url: str | None = None ) -> S3Driver:

        driver = S3Driver(bucket, options, url)

        self.register(name, driver)

        return driver

    def describe ( self ) -> dict[str, list[str]]:

        return { "drivers": self.names() }
