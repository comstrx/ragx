from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from core.error import Code, Fault
import time

def zone_of ( zone: str | tzinfo | None ) -> tzinfo:

    if zone is None: return UTC
    if isinstance(zone, tzinfo): return zone

    try: return UTC if zone.upper() == "UTC" else ZoneInfo(zone)
    except (KeyError, ValueError) as error: raise Fault(Code.BAD_REQUEST, reason=f"zone.{zone}") from error

def aware ( moment: datetime, zone: tzinfo = UTC ) -> datetime:

    return moment.replace(tzinfo=zone) if moment.tzinfo is None else moment

class Clock:

    __slots__ = ("_anchor", "_frozen", "_ticking")

    def __init__ ( self ) -> None:

        self._frozen: datetime | None = None
        self._anchor  = 0.0
        self._ticking = False

    def now ( self, zone: str | tzinfo | None = None ) -> datetime:

        chosen = zone_of(zone)

        if self._frozen is None: return datetime.now(chosen)

        moved = self._frozen

        if self._ticking: moved += timedelta(seconds=time.perf_counter() - self._anchor)

        return moved.astimezone(chosen)

    def stamp ( self ) -> float:

        return time.time() if self._frozen is None else self.now().timestamp()

    def utc ( self ) -> datetime:

        return self.now(UTC)

    def freeze ( self, at: datetime | float | None = None, ticking: bool = False ) -> datetime:

        if at is None: moment = datetime.now(UTC)
        elif isinstance(at, datetime): moment = aware(at)
        else: moment = datetime.fromtimestamp(at, UTC)

        self._frozen  = moment
        self._anchor  = time.perf_counter()
        self._ticking = ticking

        return moment

    def travel ( self, **units: float ) -> datetime:

        base = self.now(UTC)

        return self.freeze(base + timedelta(**units), self._ticking)

    def back ( self, **units: float ) -> datetime:

        return self.travel(**{ unit: -amount for unit, amount in units.items() })

    def thaw ( self ) -> None:

        self._frozen  = None
        self._ticking = False

    def frozen ( self ) -> bool:

        return self._frozen is not None

    @contextmanager
    def at ( self, moment: datetime | float | None = None, ticking: bool = False ) -> Iterator[datetime]:

        previous = (self._frozen, self._anchor, self._ticking)

        try: yield self.freeze(moment, ticking)
        finally: self._frozen, self._anchor, self._ticking = previous

    def describe ( self ) -> dict[str, object]:

        return {
            "frozen"  : self._frozen.isoformat() if self._frozen else None,
            "ticking" : self._ticking,
            "now"     : self.utc().isoformat(),
        }

clock = Clock()
