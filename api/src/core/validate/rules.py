from typing import Annotated

from pydantic import Field, StringConstraints

EMAIL    = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE    = r"^\+[1-9]\d{6,14}$"
NAME     = r"^[\w .'-]+$"
SLUG     = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
UUIDS    = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
URLS     = r"^https?://[^\s/?#]+[^\s]*$"
USERNAME = r"^[a-z0-9](?:[a-z0-9._-]{1,30}[a-z0-9])?$"
LOCALE   = r"^[a-z]{2,3}(?:[-_][A-Za-z]{2,4})?$"
CURRENCY = r"^[A-Z]{3}$"
COUNTRY  = r"^[A-Z]{2}$"
COLOR    = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
LABEL    = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
HOSTNAME = rf"^(?=.{{1,253}}$)(?:{LABEL}\.)*{LABEL}$"
TIMEZONE = r"^[A-Za-z_]+(?:/[A-Za-z_+-]+){0,2}$"
HEX      = r"^[0-9a-fA-F]+$"
DIGITS   = r"^\d+$"

def text ( pattern: str, low: int = 1, high: int = 255, lower: bool = False ) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, to_lower=lower, min_length=low, max_length=high, pattern=pattern)

Email       = Annotated[str, text(EMAIL, 3, 254, lower=True)]
Phone       = Annotated[str, StringConstraints(strip_whitespace=True, pattern=PHONE)]
Password    = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Name        = Annotated[str, text(NAME, 1, 120)]
Slug        = Annotated[str, text(SLUG, 1, 120, lower=True)]
Identifier  = Annotated[str, StringConstraints(strip_whitespace=True, pattern=UUIDS)]
Url         = Annotated[str, text(URLS, 8, 2048)]
Username    = Annotated[str, text(USERNAME, 2, 32, lower=True)]
Locale      = Annotated[str, StringConstraints(strip_whitespace=True, pattern=LOCALE)]
Currency    = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=CURRENCY)]
Country     = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=COUNTRY)]
Color       = Annotated[str, StringConstraints(strip_whitespace=True, pattern=COLOR)]
Hostname    = Annotated[str, text(HOSTNAME, 1, 253, lower=True)]
Timezone    = Annotated[str, StringConstraints(strip_whitespace=True, pattern=TIMEZONE)]
Hex         = Annotated[str, StringConstraints(strip_whitespace=True, pattern=HEX)]
Digits      = Annotated[str, StringConstraints(strip_whitespace=True, pattern=DIGITS)]
Title       = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text        = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]
Port        = Annotated[int, Field(ge=1, le=65535)]
Positive    = Annotated[int, Field(gt=0)]
NonNegative = Annotated[int, Field(ge=0)]
Percent     = Annotated[float, Field(ge=0, le=100)]
Ratio       = Annotated[float, Field(ge=0, le=1)]
Page        = Annotated[int, Field(ge=1)]
Limit       = Annotated[int, Field(ge=1, le=200)]
