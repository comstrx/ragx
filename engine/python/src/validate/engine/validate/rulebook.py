from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from engine.date import date
from engine.error import Code, Fault
from engine.net import net
from engine.parse import parse
from engine.string import string
import re

type Errors = dict[str, list[str]]
type Rules = Mapping[str, str | list[str]]
type Messages = Mapping[str, str]
type Check = Callable[["Context"], str | None]

EMPTY    : tuple[object, ...] = (None, "", [], {}, ())
ALPHA    = re.compile(r"^[^\W\d_]+$")
ALNUM    = re.compile(r"^[^\W_]+$")
DASHED   = re.compile(r"^[\w-]+$")
ACCEPTED = ("yes", "on", "1", "true", 1, True)
DECLINED = ("no", "off", "0", "false", 0, False)
SKIPPED  = ("nullable", "sometimes", "bail")
PAIR     = 2

def size_of ( value: Any ) -> float:

    if isinstance(value, bool): return float(value)
    if isinstance(value, int | float): return float(value)
    if isinstance(value, str): return float(len(value.strip()))
    if isinstance(value, list | tuple | dict | set): return float(len(value))

    return 0.0

def when ( ok: object, message: str ) -> str | None:

    return None if ok else message

@dataclass(frozen=True, slots=True)
class Context:

    field   : str
    value   : Any
    args    : list[str]
    data    : Mapping[str, Any]
    numeric : bool = False

    def text ( self ) -> str:

        return str(self.value)

    def size ( self ) -> float:

        if self.numeric and parse.is_numeric(self.value): return float(self.value)

        return size_of(self.value)

    def other ( self, index: int = 0 ) -> Any:

        return self.data.get(self.args[index]) if index < len(self.args) else None

    def limit ( self, index: int = 0 ) -> float:

        return float(self.args[index])

def span ( context: Context ) -> str | None:

    low, high = context.args[0], context.args[1]

    return when(context.limit() <= context.size() <= context.limit(1), f"Must be between {low} and {high}")

def ordered ( context: Context, earlier: bool ) -> str | None:

    target = context.data.get(context.args[0], context.args[0])

    if not (date.is_valid(context.text()) and date.is_valid(str(target))): return "Must be a valid date"

    left, right = date.parse(context.text()), date.parse(str(target))

    if earlier: return when(left < right, f"Must be before {context.args[0]}")

    return when(left > right, f"Must be after {context.args[0]}")

CHECKS: dict[str, Check] = {
    "required"    : lambda c: when(c.value not in EMPTY, "This field is required"),
    "filled"      : lambda c: when(c.value not in EMPTY, "This field must not be empty"),
    "string"      : lambda c: when(isinstance(c.value, str), "Must be a string"),
    "integer"     : lambda c: when(parse.is_int(c.value), "Must be an integer"),
    "numeric"     : lambda c: when(parse.is_numeric(c.value), "Must be a number"),
    "boolean"     : lambda c: when(parse.is_bool(c.value), "Must be true or false"),
    "array"       : lambda c: when(isinstance(c.value, list | tuple), "Must be a list"),
    "object"      : lambda c: when(isinstance(c.value, Mapping), "Must be an object"),
    "email"       : lambda c: when(string.is_email(c.text()), "Must be a valid email"),
    "url"         : lambda c: when(net.is_url(c.text()), "Must be a valid url"),
    "uuid"        : lambda c: when(parse.is_uuid(c.value), "Must be a valid uuid"),
    "ip"          : lambda c: when(net.is_ip(c.text()), "Must be a valid ip address"),
    "json"        : lambda c: when(parse.is_json(c.value), "Must be valid json"),
    "date"        : lambda c: when(date.is_valid(c.text()), "Must be a valid date"),
    "alpha"       : lambda c: when(ALPHA.match(c.text()), "Letters only"),
    "alpha_num"   : lambda c: when(ALNUM.match(c.text()), "Letters and digits only"),
    "alpha_dash"  : lambda c: when(DASHED.match(c.text()), "Letters, digits, dashes and underscores only"),
    "lowercase"   : lambda c: when(c.text() == c.text().lower(), "Must be lowercase"),
    "uppercase"   : lambda c: when(c.text() == c.text().upper(), "Must be uppercase"),
    "accepted"    : lambda c: when(c.value in ACCEPTED, "Must be accepted"),
    "declined"    : lambda c: when(c.value in DECLINED, "Must be declined"),
    "prohibited"  : lambda c: when(c.value in EMPTY, "This field is not allowed"),
    "min"         : lambda c: when(c.size() >= c.limit(), f"Must be at least {c.args[0]}"),
    "max"         : lambda c: when(c.size() <= c.limit(), f"Must be at most {c.args[0]}"),
    "between"     : span,
    "size"        : lambda c: when(c.size() == c.limit(), f"Must be exactly {c.args[0]}"),
    "digits"      : lambda c: when(c.text().isdigit() and c.size() == c.limit(), f"Must be {c.args[0]} digits"),
    "in"          : lambda c: when(c.text() in c.args, f"Must be one of: {', '.join(c.args)}"),
    "not_in"      : lambda c: when(c.text() not in c.args, "This value is not allowed"),
    "regex"       : lambda c: when(re.search(",".join(c.args), c.text()), "Invalid format"),
    "starts_with" : lambda c: when(c.text().startswith(tuple(c.args)), f"Must start with {', '.join(c.args)}"),
    "ends_with"   : lambda c: when(c.text().endswith(tuple(c.args)), f"Must end with {', '.join(c.args)}"),
    "confirmed"   : lambda c: when(c.data.get(f"{c.field}_confirmation") == c.value, "Confirmation does not match"),
    "same"        : lambda c: when(c.other() == c.value, f"Must match {c.args[0]}"),
    "different"   : lambda c: when(c.other() != c.value, f"Must differ from {c.args[0]}"),
    "gt"          : lambda c: when(c.size() > size_of(c.other()), f"Must be greater than {c.args[0]}"),
    "lt"          : lambda c: when(c.size() < size_of(c.other()), f"Must be less than {c.args[0]}"),
    "before"      : lambda c: ordered(c, earlier=True),
    "after"       : lambda c: ordered(c, earlier=False),
}

class Rulebook:

    def __init__ ( self ) -> None:

        self._checks: dict[str, Check] = dict(CHECKS)

    def extend ( self, name: str, check: Check ) -> None:

        self._checks[name] = check

    def names ( self ) -> list[str]:

        return sorted(self._checks)

    def split ( self, rules: str | list[str] ) -> list[tuple[str, list[str]]]:

        pieces = rules.split("|") if isinstance(rules, str) else list(rules)
        parsed: list[tuple[str, list[str]]] = []

        for piece in pieces:

            if not piece: continue

            name, _, raw = piece.partition(":")

            parsed.append((name.strip(), [part.strip() for part in raw.split(",")] if raw else []))

        return parsed

    def conditional ( self, name: str, args: list[str], data: Mapping[str, Any] ) -> bool:

        if name == "required_if": return len(args) >= PAIR and str(data.get(args[0])) == args[1]
        if name == "required_unless": return len(args) >= PAIR and str(data.get(args[0])) != args[1]
        if name == "required_with": return any(data.get(other) not in EMPTY for other in args)
        if name == "required_without": return any(data.get(other) in EMPTY for other in args)

        return False

    def check ( self, data: Mapping[str, Any], rules: Rules, messages: Messages | None = None ) -> Errors:

        errors: Errors = {}

        for field, spec in rules.items():

            found = self.field_errors(field, spec, data, messages or {})

            if found: errors[field] = found

        return errors

    def wording ( self, messages: Messages, field: str, rule: str, fallback: str ) -> str:

        return messages.get(f"{field}.{rule}", messages.get(rule, fallback))

    def field_errors (
        self, field: str, spec: str | list[str], data: Mapping[str, Any], messages: Messages | None = None,
    ) -> list[str]:

        said = messages or {}

        parsed = self.split(spec)
        names  = [name for name, _ in parsed]

        if "sometimes" in names and field not in data: return []

        value    = data.get(field)
        required = "required" in names or any(self.conditional(name, args, data) for name, args in parsed)

        if value in EMPTY:

            if required: return [self.wording(said, field, "required", "This field is required")]
            if "filled" in names and field in data:
                return [self.wording(said, field, "filled", "This field must not be empty")]

            return []

        numeric = "integer" in names or "numeric" in names
        found: list[str] = []

        for name, args in parsed:

            if name in SKIPPED or name.startswith("required"): continue

            check = self._checks.get(name)

            if check is None: raise Fault(Code.INTERNAL, reason=f"validate.rule.{name}")

            message = check(Context(field, value, args, data, numeric))

            if message is None: continue

            found.append(self.wording(said, field, name, message))

            if "bail" in names: break

        return found

    def validate ( self, data: Mapping[str, Any], rules: Rules, messages: Messages | None = None ) -> dict[str, Any]:

        errors = self.check(data, rules, messages)

        if errors: raise Fault(Code.VALIDATION, errors=errors)

        return { field: data[field] for field in rules if field in data }

    def passes ( self, data: Mapping[str, Any], rules: Rules ) -> bool:

        return not self.check(data, rules)

    def fails ( self, data: Mapping[str, Any], rules: Rules ) -> bool:

        return bool(self.check(data, rules))
