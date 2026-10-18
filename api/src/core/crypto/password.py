from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

class Password:

    def __init__ ( self, time_cost: int = 3, memory_cost: int = 65536, parallelism: int = 4 ) -> None:

        self._hasher = PasswordHasher(time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism)

    def hash ( self, secret: str ) -> str:
        return self._hasher.hash(secret)

    def verify ( self, secret: str, hashed: str ) -> bool:

        try: return self._hasher.verify(hashed, secret)
        except (VerifyMismatchError, VerificationError, InvalidHashError): return False

    def stale ( self, hashed: str ) -> bool:

        try: return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError: return True

    def is_hash ( self, text: str ) -> bool:
        return text.startswith("$argon2")

    def describe ( self ) -> dict[str, int]:

        return {
            "time_cost": self._hasher.time_cost, "memory_cost": self._hasher.memory_cost,
            "parallelism": self._hasher.parallelism,
        }
