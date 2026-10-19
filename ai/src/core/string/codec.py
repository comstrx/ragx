from core.error import Code, Fault
import base64, binascii, secrets, string

ALPHABET = string.ascii_letters + string.digits
BASE64   = "string.base64"
HEX      = "string.hex"

class Codec:

    def to_base64 ( self, data: str | bytes, url: bool = False ) -> str:

        raw = data.encode() if isinstance(data, str) else data

        return (base64.urlsafe_b64encode(raw) if url else base64.b64encode(raw)).decode()

    def from_base64 ( self, text: str, url: bool = False ) -> bytes:

        padded = text + "=" * (-len(text) % 4)

        try: return base64.urlsafe_b64decode(padded) if url else base64.b64decode(padded, validate=True)
        except (ValueError, binascii.Error) as error: raise Fault(Code.BAD_REQUEST, reason=BASE64) from error

    def to_hex ( self, data: str | bytes ) -> str:

        return (data.encode() if isinstance(data, str) else data).hex()

    def from_hex ( self, text: str ) -> bytes:

        try: return bytes.fromhex(text)
        except ValueError as error: raise Fault(Code.BAD_REQUEST, reason=HEX) from error

    def to_bytes ( self, text: str, encoding: str = "utf-8" ) -> bytes:

        return text.encode(encoding)

    def from_bytes ( self, data: bytes, encoding: str = "utf-8" ) -> str:

        return data.decode(encoding, errors="replace")

    def random ( self, size: int = 16, alphabet: str = ALPHABET ) -> str:

        return "".join(secrets.choice(alphabet) for _ in range(size))

    def token ( self, size: int = 32 ) -> str:

        return secrets.token_urlsafe(size)

    def escape_html ( self, text: str ) -> str:

        return (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#x27;")
        )

    def quote ( self, text: str, mark: str = '"' ) -> str:

        return f"{mark}{text}{mark}"

    def unquote ( self, text: str ) -> str:

        if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'": return text[1:-1]

        return text
