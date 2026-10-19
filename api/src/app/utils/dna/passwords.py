from core.crypto import crypto
from core.error import Code, Fault
from core.rand import rand
from core.thread import thread

WEAK = ("password", "12345678", "qwerty123", "letmein1")

class Passwords:

    def __init__ ( self ) -> None:

        self._decoy: str | None = None

    async def decoy ( self ) -> str:

        if self._decoy is None: self._decoy = await thread.offload(crypto.hash, rand.token(24))

        return self._decoy

    async def hash ( self, password: str ) -> str:

        if password.lower() in WEAK:
            raise Fault(Code.VALIDATION, errors={ "password": ["This password is too common"] })

        return await thread.offload(crypto.hash, password)

    async def verify ( self, password: str, hashed: str | None ) -> bool:

        matched = await thread.offload(crypto.verify, password, hashed or await self.decoy())

        return hashed is not None and matched

    def stale ( self, hashed: str ) -> bool:

        return crypto.stale(hashed)
