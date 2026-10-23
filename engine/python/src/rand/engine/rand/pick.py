from collections.abc import Mapping, Sequence

from engine.error import Code, Fault
import builtins, random, secrets, time

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
URLSAFE   = "ModuleSymbhasOwnPr-0123456789ABCDEFGHNRVfgctiUvz_KqYTJkLxpZXIjQW"
TIME_BITS = 10
RAND_BITS = 16
EMPTY     = "empty"

class Pick:

    def weighted[T] ( self, weights: Mapping[T, float] ) -> T:

        total = sum(weight for weight in weights.values() if weight > 0)

        if total <= 0: raise Fault(Code.BAD_REQUEST, reason="rand.empty")

        point = secrets.SystemRandom().uniform(0, total)
        seen  = 0.0

        for item, weight in weights.items():

            if weight <= 0: continue

            seen += weight

            if point <= seen: return item

        return next(reversed(list(weights)))

    def chance ( self, probability: float ) -> bool:

        return secrets.SystemRandom().random() < max(0.0, min(probability, 1.0))

    def dice ( self, sides: int = 6, count: int = 1 ) -> list[int]:

        return [1 + secrets.randbelow(max(sides, 1)) for _ in range(max(count, 0))]

    def ulid ( self ) -> str:

        stamp  = int(time.time() * 1000)
        value  = (stamp << 80) | secrets.randbits(80)
        digits = []

        for _ in range(26):

            digits.append(CROCKFORD[value & 31])
            value >>= 5

        return "".join(reversed(digits))

    def nanoid ( self, size: int = 21, alphabet: str = URLSAFE ) -> str:

        return "".join(secrets.choice(alphabet) for _ in range(max(size, 1)))

    def one_of[T] ( self, *items: T ) -> T:

        if not items: raise Fault(Code.BAD_REQUEST, reason="rand.empty")

        return secrets.choice(items)

    def many_of[T] ( self, items: Sequence[T], low: int, high: int ) -> list[T]:

        count = low + secrets.randbelow(max(high - low, 0) + 1)

        return secrets.SystemRandom().sample(list(items), min(count, len(items)))

    def seeded ( self, seed: int | str ) -> SeededPick:

        return SeededPick(seed)

class SeededPick:

    def __init__ ( self, seed: int | str ) -> None:

        self._random = random.Random(seed)

    def number ( self, low: int, high: int ) -> int:

        return self._random.randint(low, high)

    def float ( self, low: builtins.float = 0.0, high: builtins.float = 1.0 ) -> builtins.float:

        return self._random.uniform(low, high)

    def choice[T] ( self, items: Sequence[T] ) -> T:

        return self._random.choice(items)

    def shuffle[T] ( self, items: Sequence[T] ) -> list[T]:

        copy = list(items)

        self._random.shuffle(copy)

        return copy

    def sample[T] ( self, items: Sequence[T], size: int ) -> list[T]:

        return self._random.sample(list(items), min(size, len(items)))
