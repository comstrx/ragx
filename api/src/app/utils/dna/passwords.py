from core.crypto import crypto
from core.exceptions import Code, Fault
from core.thread import thread

WEAK = ("password", "12345678", "qwerty123", "letmein1")

class Passwords:

    async def hash ( self, password: str ) -> str:

        if password.lower() in WEAK:
            raise Fault(Code.VALIDATION, errors={ "password": ["This password is too common"] })

        return await thread.offload(crypto.hash, password)

    async def verify ( self, password: str, hashed: str | None ) -> bool:
        return hashed is not None and await thread.offload(crypto.verify, password, hashed)

    def stale ( self, hashed: str ) -> bool:
        return crypto.stale(hashed)
