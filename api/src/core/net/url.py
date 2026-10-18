from collections.abc import Mapping
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

type Query = Mapping[str, object]

SCHEMES = ("http", "https")
PORTS   = { "http": 80, "https": 443 }
PARTS   = 2

class Url:

    def url ( self, base: str, *parts: str, **query: object ) -> str:

        path = "/".join(part.strip("/") for part in parts if part)
        full = urljoin(base.rstrip("/") + "/", path) if path else base
        tail = self.query_of(query)

        return f"{full}?{urlencode(tail)}" if tail else full

    def join ( self, base: str, path: str ) -> str:
        return urljoin(base.rstrip("/") + "/", path.lstrip("/"))

    def origin ( self, url: str ) -> str:

        parts = urlsplit(url)

        return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""

    def scheme ( self, url: str ) -> str:
        return urlsplit(url).scheme

    def host ( self, url: str ) -> str:
        return urlsplit(url).hostname or ""

    def port ( self, url: str ) -> int | None:

        parts = urlsplit(url)

        return parts.port or PORTS.get(parts.scheme)

    def path ( self, url: str ) -> str:
        return urlsplit(url).path or "/"

    def fragment ( self, url: str ) -> str:
        return urlsplit(url).fragment

    def query ( self, url: str ) -> dict[str, str]:
        return dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))

    def query_all ( self, url: str ) -> dict[str, list[str]]:

        found: dict[str, list[str]] = {}

        for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
            found.setdefault(key, []).append(value)

        return found

    def with_query ( self, url: str, **params: object ) -> str:

        parts = urlsplit(url)
        merged = { **dict(parse_qsl(parts.query, keep_blank_values=True)), **self.query_of(params) }

        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment))

    def without_query ( self, url: str ) -> str:

        parts = urlsplit(url)

        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def with_path ( self, url: str, path: str ) -> str:

        parts = urlsplit(url)

        return urlunsplit((parts.scheme, parts.netloc, "/" + path.lstrip("/"), parts.query, parts.fragment))

    def normalize ( self, url: str ) -> str:

        parts = urlsplit(url.strip())
        host  = (parts.hostname or "").lower()
        port  = f":{parts.port}" if parts.port and parts.port != PORTS.get(parts.scheme) else ""
        path  = parts.path or "/"

        return urlunsplit((parts.scheme.lower(), f"{host}{port}", path, parts.query, ""))

    def domain ( self, host_or_url: str ) -> str:

        host  = self.host(host_or_url) if "://" in host_or_url else host_or_url
        parts = host.lower().strip(".").split(".")

        return ".".join(parts[-PARTS:]) if len(parts) >= PARTS else host

    def subdomain ( self, host_or_url: str ) -> str:

        host  = self.host(host_or_url) if "://" in host_or_url else host_or_url
        parts = host.lower().strip(".").split(".")

        return ".".join(parts[:-PARTS]) if len(parts) > PARTS else ""

    def is_url ( self, text: str ) -> bool:

        parts = urlsplit(text)

        return parts.scheme in SCHEMES and bool(parts.netloc)

    def is_secure ( self, url: str ) -> bool:
        return urlsplit(url).scheme == "https"

    def is_absolute ( self, text: str ) -> bool:
        return bool(urlsplit(text).scheme)

    def encode ( self, text: str, safe: str = "" ) -> str:
        return quote(text, safe=safe)

    def decode ( self, text: str ) -> str:
        return unquote(text)

    def query_of ( self, params: Query | None ) -> dict[str, str]:
        return { key: str(value) for key, value in (params or {}).items() if value is not None }

    def parts ( self, url: str ) -> dict[str, object]:

        return {
            "scheme": self.scheme(url), "host": self.host(url), "port": self.port(url), "path": self.path(url),
            "query": self.query(url), "fragment": self.fragment(url),
        }
