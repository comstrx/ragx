from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.date import Moment, date
from core.json import json
from core.number import number
from core.string import string

type Filter = Callable[..., Any]

def ago ( value: datetime | Moment | str ) -> str:
    return date.moment(value).human()

def when ( value: datetime | Moment | str, pattern: str = "YYYY-MM-DD" ) -> str:
    return date.moment(value).format(pattern)

def pretty ( value: object ) -> str:
    return json.pretty(value)

class Filters:

    def all ( self ) -> dict[str, Filter]:

        return {
            "slug"          : string.slug,
            "truncate_text" : string.truncate,
            "title_case"    : string.title,
            "headline"      : string.headline,
            "plural"        : string.plural,
            "mask"          : string.mask,
            "iso"           : date.iso,
            "ago"           : ago,
            "when"          : when,
            "human"         : number.human,
            "bytes"         : number.bytes,
            "percent"       : number.percent,
            "ordinal"       : number.ordinal,
            "thousands"     : number.thousands,
            "currency"      : number.currency,
            "pretty"        : pretty,
        }

    def globals ( self ) -> dict[str, Any]:
        return { "now": date.now, "today": date.today }
