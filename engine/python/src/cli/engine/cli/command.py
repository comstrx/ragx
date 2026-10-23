from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, Self

from engine.error import Code, Fault

type Run = Callable[..., Any]
type Place = Literal["argument", "option", "flag"]

REQUIRED = object()
KINDS    = (str, int, float, bool)

@dataclass(frozen=True, slots=True)
class Input:

    name    : str
    place   : Place
    kind    : type = str
    default : Any = REQUIRED
    about   : str = ""
    short   : str | None = None

    def required ( self ) -> bool:

        return self.default is REQUIRED

    def switch ( self ) -> str:

        return f"--{self.name.replace('_', '-')}"

    def label ( self ) -> str:

        if self.place == "argument": return f"<{self.name}>" if self.required() else f"[{self.name}]"

        named = f"{self.short}, {self.switch()}" if self.short else self.switch()

        return named if self.place == "flag" else f"{named} <{self.kind.__name__}>"

@dataclass(frozen=True, slots=True)
class Command:

    name     : str
    run      : Run
    about    : str = ""
    group    : str = "general"
    inputs   : tuple[Input, ...] = ()
    aliases  : tuple[str, ...] = ()
    examples : tuple[str, ...] = ()

    def argument ( self, name: str, kind: type = str, default: Any = REQUIRED, about: str = "" ) -> Self:

        return self.adding(Input(name, "argument", kind, default, about))

    def option (
        self, name: str, kind: type = str, default: Any = None, about: str = "", short: str | None = None,
    ) -> Self:

        return self.adding(Input(name, "option", kind, default, about, short))

    def flag ( self, name: str, about: str = "", short: str | None = None ) -> Self:

        return self.adding(Input(name, "flag", bool, default=False, about=about, short=short))

    def alias ( self, *names: str ) -> Self:

        return replace(self, aliases=(*self.aliases, *names))

    def example ( self, *lines: str ) -> Self:

        return replace(self, examples=(*self.examples, *lines))

    def adding ( self, given: Input ) -> Self:

        if given.kind not in KINDS: raise Fault(Code.INTERNAL, reason="cli.kind")
        if any(known.name == given.name for known in self.inputs): raise Fault(Code.INTERNAL, reason="cli.duplicate")

        trailing = [known for known in self.inputs if known.place == "argument" and not known.required()]

        if given.place == "argument" and given.required() and trailing:
            raise Fault(Code.INTERNAL, reason="cli.order")

        return replace(self, inputs=(*self.inputs, given))

    def names ( self ) -> tuple[str, ...]:

        return (self.name, *self.aliases)

    def usage ( self ) -> str:

        return " ".join([self.name, *(item.label() for item in self.inputs)])

    def describe ( self ) -> dict[str, Any]:

        return {
            "name": self.name, "about": self.about, "group": self.group, "aliases": list(self.aliases),
            "inputs": [item.name for item in self.inputs], "usage": self.usage(),
        }

def grouped ( commands: Sequence[Command] ) -> dict[str, list[Command]]:

    groups: dict[str, list[Command]] = {}

    for command in commands: groups.setdefault(command.group, []).append(command)

    return groups
