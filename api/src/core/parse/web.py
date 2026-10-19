from collections.abc import Iterable
from urllib.parse import parse_qsl, unquote_plus

import base64, binascii, re

PARAM   = re.compile(r';\s*([^=;\s]+)\s*=\s*("(?:[^"\\]|\\.)*"|[^;]*)')
QUALITY = re.compile(r"^\s*q\s*=\s*([01](?:\.\d{0,3})?)\s*$")
PAIR    = 2
TOKEN   = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")

def unquoted ( value: str ) -> str:

    value = value.strip()

    if len(value) >= PAIR and value[0] == value[-1] == '"': return re.sub(r"\\(.)", r"\1", value[1:-1])

    return value

class Web:

    def content_type ( self, header: str | None ) -> tuple[str, dict[str, str]]:

        raw = (header or "").strip()

        if not raw: return "", {}

        kind, _, rest = raw.partition(";")

        return kind.strip().lower(), self.header_params(f";{rest}" if rest else "")

    def media ( self, header: str | None ) -> str:

        return self.content_type(header)[0]

    def charset ( self, header: str | None, default: str = "utf-8" ) -> str:

        return self.content_type(header)[1].get("charset", default).lower()

    def header_params ( self, text: str ) -> dict[str, str]:

        return { name.lower(): unquoted(value) for name, value in PARAM.findall(text) }

    def disposition ( self, header: str | None ) -> tuple[str, dict[str, str]]:

        return self.content_type(header)

    def accept ( self, header: str | None ) -> list[tuple[str, float]]:

        ranked: list[tuple[str, float, int]] = []

        for order, part in enumerate((header or "").split(",")):

            value, *params = [piece.strip() for piece in part.split(";")]

            if not value: continue

            weight = 1.0

            for param in params:

                found = QUALITY.match(param)

                if found: weight = float(found.group(1))

            if weight > 0: ranked.append((value.lower(), weight, order))

        ranked.sort(key=lambda item: (-item[1], item[2]))

        return [(value, weight) for value, weight, _ in ranked]

    def prefers ( self, header: str | None, offered: Iterable[str] ) -> str | None:

        choices = list(offered)

        for wanted, _ in self.accept(header):

            for offer in choices:

                major, _, minor = wanted.partition("/")
                kind, _, sub    = offer.lower().partition("/")

                if wanted in ("*", "*/*") or wanted == offer.lower(): return offer
                if minor == "*" and major == kind and sub: return offer

        return None

    def query ( self, text: str | None ) -> dict[str, str | list[str]]:

        found: dict[str, str | list[str]] = {}

        for key, value in parse_qsl((text or "").lstrip("?"), keep_blank_values=True):

            name = key.removesuffix("[]")

            if key.endswith("[]") or name in found:

                held = found.get(name)

                found[name] = [*(held if isinstance(held, list) else [held] if held is not None else []), value]

            else: found[name] = value

        return found

    def cookies ( self, header: str | None ) -> dict[str, str]:

        jar: dict[str, str] = {}

        for part in (header or "").split(";"):

            name, separator, value = part.partition("=")

            if separator and TOKEN.match(name.strip()): jar[name.strip()] = unquote_plus(unquoted(value))

        return jar

    def bearer ( self, header: str | None ) -> str | None:

        scheme, _, token = (header or "").strip().partition(" ")

        return token.strip() or None if scheme.lower() == "bearer" else None

    def basic ( self, header: str | None ) -> tuple[str, str] | None:

        scheme, _, token = (header or "").strip().partition(" ")

        if scheme.lower() != "basic" or not token: return None

        try: decoded = base64.b64decode(token.strip(), validate=True).decode()
        except (binascii.Error, UnicodeDecodeError): return None

        user, separator, secret = decoded.partition(":")

        return (user, secret) if separator else None

    def forwarded ( self, header: str | None ) -> list[str]:

        return [hop.strip() for hop in (header or "").split(",") if hop.strip()]
