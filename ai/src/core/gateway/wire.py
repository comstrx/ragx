from collections.abc import Mapping
from typing import Any

from core.date import date

def form ( value: object, prefix: str = "" ) -> dict[str, str]:

    flat: dict[str, str] = {}

    if isinstance(value, Mapping):
        for key, item in value.items(): flat.update(form(item, f"{prefix}[{key}]" if prefix else str(key)))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value): flat.update(form(item, f"{prefix}[{index}]"))
    elif isinstance(value, bool): flat[prefix] = "true" if value else "false"
    elif value is not None: flat[prefix] = str(value)

    return flat

def mapping ( value: object ) -> dict[str, Any]:

    return dict(value) if isinstance(value, Mapping) else {}

def stamped ( value: object ) -> str | None:

    return date.iso(date.from_stamp(float(str(value)))) if isinstance(value, int | float) and value else None
