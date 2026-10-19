from typing import Annotated

from .rule import Rule

PHONE    = r"^\+[1-9]\d{6,14}$"
NAME     = r"^[\w .'-]+$"
SLUG     = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
USERNAME = r"^[a-z0-9](?:[a-z0-9._-]{0,30}[a-z0-9])?$"
LOCALE   = r"^[a-z]{2,3}(?:[-_][A-Za-z]{2,4})?$"
CURRENCY = r"^[A-Z]{3}$"
COUNTRY  = r"^[A-Z]{2}$"
COLOR    = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
LABEL    = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
HOSTNAME = rf"^(?=.{{1,253}}$)(?:{LABEL}\.)*{LABEL}$"
TIMEZONE = r"^[A-Za-z_]+(?:/[A-Za-z_+-]+){0,2}$"
HEX      = r"^[0-9a-fA-F]+$"
DIGITS   = r"^\d+$"
TEXT     = Rule().string().trim()

Email       = Annotated[str, TEXT.lower().email().between(3, 254)]
Phone       = Annotated[str, TEXT.latin_digits().regex(PHONE)]
Password    = Annotated[str, Rule().string().between(8, 128)]
Name        = Annotated[str, TEXT.squish().regex(NAME).between(1, 120)]
Slug        = Annotated[str, TEXT.lower().regex(SLUG).between(1, 120)]
Identifier  = Annotated[str, TEXT.lower().uuid()]
Url         = Annotated[str, TEXT.url().between(8, 2048)]
Username    = Annotated[str, TEXT.lower().regex(USERNAME).between(2, 32)]
Locale      = Annotated[str, TEXT.regex(LOCALE)]
Currency    = Annotated[str, TEXT.upper().regex(CURRENCY)]
Country     = Annotated[str, TEXT.upper().regex(COUNTRY)]
Color       = Annotated[str, TEXT.regex(COLOR)]
Hostname    = Annotated[str, TEXT.lower().regex(HOSTNAME).between(1, 253)]
Timezone    = Annotated[str, TEXT.regex(TIMEZONE)]
Hex         = Annotated[str, TEXT.regex(HEX)]
Digits      = Annotated[str, TEXT.latin_digits().regex(DIGITS)]
Title       = Annotated[str, TEXT.squish().between(1, 200)]
Text        = Annotated[str, TEXT.between(1, 10_000)]
Port        = Annotated[int, Rule().integer().between(1, 65535)]
Positive    = Annotated[int, Rule().integer().min(1)]
NonNegative = Annotated[int, Rule().integer().min(0)]
Percent     = Annotated[float, Rule().numeric().between(0, 100)]
Ratio       = Annotated[float, Rule().numeric().between(0, 1)]
Page        = Annotated[int, Rule().integer().min(1)]
Limit       = Annotated[int, Rule().integer().between(1, 200)]
