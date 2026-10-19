from collections.abc import AsyncIterator

from core.storage import Stored, Uploaded, storage
from app.models import User
from app.utils.cycle import Service

class FilesService(Service):

    async def publish ( self, file: Uploaded, user: User ) -> Stored:

        stored = await storage.upload(file, "uploads", disk="public")

        self.log.info("files.published", user=str(user.id), path=stored.path, size=stored.size)

        return stored

    async def keep ( self, file: Uploaded, user: User ) -> Stored:

        stored = await storage.upload(file, f"users/{user.id}", disk="private", pattern="")

        self.log.info("files.kept", user=str(user.id), path=stored.path, size=stored.size)

        return stored

    async def open ( self, path: str, user: User ) -> tuple[AsyncIterator[bytes], str]:

        if not path.startswith(f"users/{user.id}/"): path = f"users/{user.id}/{path}"

        return await storage.stream(path, "private"), storage.mime(path)
