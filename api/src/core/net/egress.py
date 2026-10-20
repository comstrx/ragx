from collections.abc import Awaitable, Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import override

from core.error import Code, Fault
from .client import Client
from .reply import Transport
import asyncio, httpx, ipaddress, socket

type Resolver = Callable[[str, int], Awaitable[Sequence[str]]]
type Address = ipaddress.IPv4Address | ipaddress.IPv6Address

PORTS     = { "https": 443, "http": 80 }
UNREACHED = (httpx.ConnectError, httpx.ConnectTimeout)

async def lookup ( host: str, port: int ) -> list[str]:

    found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)

    return list(dict.fromkeys(str(item[4][0]) for item in found))

def unmapped ( text: str ) -> Address:

    found = ipaddress.ip_address(text.split("%", 1)[0])

    if isinstance(found, ipaddress.IPv6Address) and found.ipv4_mapped is not None: return found.ipv4_mapped

    return found

@dataclass(frozen=True, slots=True)
class Egress:

    schemes   : frozenset[str] = frozenset({"https"})
    hosts     : frozenset[str] = frozenset()
    ports     : frozenset[int] = field(default_factory=lambda: frozenset(PORTS.values()))
    private   : bool = False
    redirects : int = 3

    @classmethod
    def of (
        cls, schemes: Iterable[str] = ("https",), hosts: Iterable[str] = (), private: bool = False, redirects: int = 3,
    ) -> Egress:

        return cls(frozenset(schemes), frozenset(host.lower() for host in hosts), private=private, redirects=redirects)

    def allows ( self, address: str ) -> bool:

        try: found = unmapped(address)
        except ValueError: return False

        if found.is_link_local or found.is_multicast or found.is_unspecified: return False
        if self.private and (found.is_loopback or found.is_private): return True

        return found.is_global and not found.is_reserved

    def _target_ ( self, url: httpx.URL ) -> tuple[str, int]:

        host = url.host.lower()
        port = url.port or PORTS.get(url.scheme, 0)

        if url.scheme not in self.schemes: raise Fault(Code.FORBIDDEN, reason="net.egress.scheme")
        if url.userinfo or not host: raise Fault(Code.FORBIDDEN, reason="net.egress.url")
        if self.hosts and host not in self.hosts: raise Fault(Code.FORBIDDEN, reason="net.egress.host")
        if port not in self.ports: raise Fault(Code.FORBIDDEN, reason="net.egress.port")

        return host, port

    def client ( self, wait: float = 20.0, transport: Transport | None = None, resolver: Resolver = lookup ) -> Client:

        inner  = transport.inner if transport is not None else httpx.AsyncHTTPTransport(retries=0)
        pinned = Pinned(self, inner, resolver)

        return Client(wait=wait, transport=Transport(pinned)).outbound(self.redirects)

class Pinned(httpx.AsyncBaseTransport):

    def __init__ ( self, egress: Egress, inner: httpx.AsyncBaseTransport, resolver: Resolver ) -> None:

        self._egress   = egress
        self._inner    = inner
        self._resolver = resolver
        self.refused   = 0

    async def addresses ( self, host: str, port: int ) -> list[str]:

        try: found = list(await self._resolver(host, port))
        except OSError as error: raise Fault(Code.UNAVAILABLE, reason="net.egress.dns") from error

        if not found or not all(map(self._egress.allows, found)):

            self.refused += 1

            raise Fault(Code.FORBIDDEN, reason="net.egress.address")

        return found

    @override
    async def handle_async_request ( self, request: httpx.Request ) -> httpx.Response:

        host, port    = self._egress._target_(request.url)
        *others, last = await self.addresses(host, port)
        target        = request.url
        default       = port == PORTS.get(target.scheme)

        request.headers["host"]            = host if default else f"{host}:{port}"
        request.extensions["sni_hostname"] = host

        for address in others:

            request.url = target.copy_with(host=str(unmapped(address)))

            with suppress(*UNREACHED): return await self._inner.handle_async_request(request)

        request.url = target.copy_with(host=str(unmapped(last)))

        return await self._inner.handle_async_request(request)

    @override
    async def aclose ( self ) -> None:

        await self._inner.aclose()
