from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from core.error import Code, Fault
import httpx, ipaddress, socket, asyncio

HTTP_OK = 200
REDIRECTS = frozenset({301, 302, 303, 307, 308})

@dataclass(frozen=True, slots=True)
class DownloadPolicy:

    hosts          : tuple[str, ...] = ("huggingface.co", "github.com", "release-assets.githubusercontent.com",
                                      "us.aws.cdn.hf.co", "cdn-lfs.huggingface.co", "cdn-lfs-us-1.hf.co",
                                      "cas-bridge.xethub.hf.co")
    allow_loopback : bool = False
    timeout        : float = 60.0
    redirects      : int = 6

    async def validate ( self, url: str ) -> str:

        parsed = urlsplit(url)
        host = parsed.hostname or ""
        local = self.allow_loopback and host in ("localhost", "127.0.0.1", "::1")

        if parsed.username or parsed.password or parsed.fragment:
            raise Fault(Code.FORBIDDEN, reason="download.url")
        if not local and (parsed.scheme != "https" or host not in self.hosts or parsed.port not in (None, 443)):
            raise Fault(Code.FORBIDDEN, reason="download.origin", errors={"host": [host]})
        if local:
            if parsed.scheme not in ("http", "https"): raise Fault(Code.FORBIDDEN, reason="download.scheme")
            return host

        addresses = await asyncio.get_running_loop().getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)

        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise Fault(Code.FORBIDDEN, reason="download.address")

        return str(next((item[4][0] for item in addresses if item[0] == socket.AF_INET), addresses[0][4][0]))

class Downloads:

    def __init__ ( self, policy: DownloadPolicy | None = None ) -> None:

        self.policy = policy or DownloadPolicy()

    async def chunks ( self, url: str ) -> AsyncIterator[bytes]:

        async with httpx.AsyncClient(
            timeout=self.policy.timeout, follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            try:
                for _ in range(self.policy.redirects + 1):
                    address = await self.policy.validate(url)
                    original = httpx.URL(url)
                    headers = {"accept-encoding": "identity", "host": original.netloc.decode()}
                    async with client.stream(
                        "GET", original.copy_with(host=address), headers=headers,
                        extensions={"sni_hostname": original.host},
                    ) as reply:
                        if reply.status_code in REDIRECTS:
                            destination = reply.headers.get("location")
                            if not destination: raise Fault(Code.UNAVAILABLE, reason="download.redirect")
                            url = urljoin(url, destination)
                            continue
                        if reply.status_code != HTTP_OK: raise Fault(Code.UNAVAILABLE, reason="download.http")
                        if reply.headers.get("content-encoding", "identity") != "identity":
                            raise Fault(Code.VALIDATION, reason="download.encoding")
                        async for chunk in reply.aiter_bytes(256 * 1024): yield chunk
                        return
                raise Fault(Code.UNAVAILABLE, reason="download.redirect.limit")
            except (httpx.HTTPError, OSError) as error:
                raise Fault(Code.UNAVAILABLE, reason="download.network") from error
