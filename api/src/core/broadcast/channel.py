from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from core.socket import Grant
import re

type Verdict = Grant | Mapping[str, Any] | bool | None
type Authorize = Callable[..., Awaitable[Verdict] | Verdict]

PRIVATE  = "private-"
PRESENCE = "presence-"
PARAM    = re.compile(r"\{(\w+)\}")

@dataclass(frozen=True, slots=True)
class Channel:

    pattern   : str
    matcher   : re.Pattern[str]
    authorize : Authorize | None
    guests    : bool = False

    def match ( self, name: str ) -> dict[str, str] | None:

        found = self.matcher.fullmatch(name)

        return found.groupdict() if found else None

    def params ( self ) -> list[str]:
        return PARAM.findall(self.pattern)

    def describe ( self ) -> dict[str, Any]:
        return { "pattern": self.pattern, "guests": self.guests, "guarded": self.authorize is not None }

class Channels:

    def __init__ ( self ) -> None:

        self._channels: list[Channel] = []

    def channel ( self, pattern: str, authorize: Authorize | None = None, guests: bool = False ) -> Channel:

        escaped = re.escape(pattern).replace(r"\{", "{").replace(r"\}", "}")
        regex   = PARAM.sub(lambda found: f"(?P<{found.group(1)}>[^.]+)", escaped)
        channel = Channel(pattern, re.compile(regex), authorize, guests)

        self._channels.append(channel)

        return channel

    def public ( self, pattern: str ) -> Channel:
        return self.channel(pattern, None, guests=True)

    def patterns ( self ) -> list[str]:
        return [channel.pattern for channel in self._channels]

    def all ( self ) -> list[Channel]:
        return list(self._channels)

    def forget ( self, pattern: str ) -> bool:

        before = len(self._channels)

        self._channels = [channel for channel in self._channels if channel.pattern != pattern]

        return len(self._channels) < before

    def clear ( self ) -> None:
        self._channels.clear()

    def find ( self, name: str ) -> tuple[Channel, dict[str, str]] | None:

        for channel in self._channels:

            params = channel.match(name)

            if params is not None: return channel, params

        return None

    def kind ( self, name: str ) -> str:

        if name.startswith(PRESENCE): return "presence"
        if name.startswith(PRIVATE): return "private"

        return "public"

    def bare ( self, name: str ) -> str:

        for prefix in (PRESENCE, PRIVATE):
            if name.startswith(prefix): return name[len(prefix):]

        return name

    def describe ( self ) -> list[dict[str, Any]]:
        return [channel.describe() for channel in self._channels]
