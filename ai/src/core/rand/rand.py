from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid7

from core.error import Code, Fault
from .fake import Fake
from .pick import Pick
import secrets, string

ALPHANUMERIC = string.ascii_letters + string.digits
LOWER        = string.ascii_lowercase + string.digits
SAFE         = "abcdefghjkmnpqrstuvwxyz23456789"
DIGITS       = string.digits
SYMBOLS      = "!@#$%^&*-_=+"
VERSIONS     = (4, 7)
STRONGEST    = 7
YEAR         = 365
EMPTY        = "empty"
PASSWORD     = 16

class Rand(Pick, Fake):

    def __init__ ( self ) -> None:

        super().__init__()

    def uuid ( self, version: int = 7 ) -> UUID:

        if version not in VERSIONS: raise Fault(Code.BAD_REQUEST, reason=f"rand.uuid.{version}")

        return uuid7() if version == STRONGEST else uuid4()

    def uuid_text ( self, version: int = 7 ) -> str:

        return str(self.uuid(version))

    def string ( self, size: int = 16, alphabet: str = ALPHANUMERIC ) -> str:

        return "".join(secrets.choice(alphabet) for _ in range(max(size, 0)))

    def slug ( self, size: int = 10 ) -> str:

        return self.string(size, LOWER)

    def code ( self, size: int = 8 ) -> str:

        return self.string(size, SAFE)

    def otp ( self, digits: int = 6 ) -> str:

        return self.string(digits, DIGITS)

    def token ( self, size: int = 32 ) -> str:

        return secrets.token_urlsafe(size)

    def hex ( self, size: int = 16 ) -> str:

        return secrets.token_hex(size)

    def bytes ( self, size: int = 32 ) -> bytes:

        return secrets.token_bytes(size)

    def password ( self, size: int = PASSWORD, symbols: bool = True ) -> str:

        pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, *( [SYMBOLS] if symbols else [] )]
        picks = [secrets.choice(pool) for pool in pools]
        rest  = [secrets.choice("".join(pools)) for _ in range(max(size - len(picks), 0))]

        return "".join(self.shuffle([*picks, *rest]))

    def number ( self, low: int, high: int ) -> int:

        if high < low: raise Fault(Code.BAD_REQUEST, reason="rand.range")

        return low + secrets.randbelow(high - low + 1)

    def float ( self, low: float = 0.0, high: float = 1.0 ) -> float:

        return self._system.uniform(low, high)

    def bool ( self ) -> bool:

        return secrets.randbelow(2) == 1

    def choice[T] ( self, items: Sequence[T] ) -> T:

        if not items: raise Fault(Code.BAD_REQUEST, reason="rand.empty")

        return secrets.choice(items)

    def sample[T] ( self, items: Sequence[T], size: int ) -> list[T]:

        return self._system.sample(list(items), min(size, len(items)))

    def shuffle[T] ( self, items: Sequence[T] ) -> list[T]:

        copy = list(items)

        self._system.shuffle(copy)

        return copy

    def date ( self, start: datetime | None = None, end: datetime | None = None ) -> datetime:

        last  = end or datetime.now(UTC)
        first = start or last - timedelta(days=YEAR)

        if first > last: raise Fault(Code.BAD_REQUEST, reason="rand.range")

        return first + timedelta(seconds=self._system.uniform(0, (last - first).total_seconds()))

    def color ( self ) -> str:

        return f"#{secrets.randbits(24):06x}"

    def pin ( self, digits: int = 4 ) -> str:

        return self.otp(digits)
