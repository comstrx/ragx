from collections.abc import Callable, Sequence
from typing import Any, NoReturn, Self, TextIO, override

from core.error import Code, Fault
from core.parse import parse
from core.string import string
from core.thread import thread
from .command import Command, Input, grouped
import argparse, inspect, sys

USAGE  = 2
FAILED = 1
HELP   = frozenset({"-h", "--help", "help"})
SHOW   = frozenset({"-V", "--version"})

class Parser(argparse.ArgumentParser):

    @override
    def error ( self, message: str ) -> NoReturn:

        raise Fault(Code.BAD_REQUEST, message, "cli.usage")

def converter ( kind: type ) -> Callable[[str], Any]:

    if kind is bool: return parse.bool

    return kind

class Cli:

    def __init__ (
        self, name: str, about: str = "", version: str = "", default: str | None = None,
        out: TextIO | None = None, err: TextIO | None = None,
    ) -> None:

        self._name     = name
        self._about    = about
        self._version  = version
        self._default  = default
        self._out      = out or sys.stdout
        self._err      = err or sys.stderr
        self._commands : dict[str, Command] = {}

    def add ( self, *commands: Command ) -> Self:

        for command in commands:

            taken = [name for name in command.names() if name in self.names(aliases=True)]

            if taken: raise Fault(Code.INTERNAL, reason="cli.taken")

            self._commands[command.name] = command

        return self

    def names ( self, aliases: bool = False ) -> list[str]:

        if not aliases: return sorted(self._commands)

        return sorted(name for command in self._commands.values() for name in command.names())

    def find ( self, name: str ) -> Command | None:

        return next((command for command in self._commands.values() if name in command.names()), None)

    def run ( self, argv: Sequence[str] | None = None ) -> int:

        given = sys.argv[1:] if argv is None else list(argv)
        args  = given or ([self._default] if self._default else [])

        if not args or args[0] in HELP: return self.say(self.help(args[1] if len(args) > 1 else None))
        if args[0] in SHOW: return self.say(f"{self._name} {self._version}".strip())

        command = self.find(args[0])

        if command is None: return self.refuse(self.unknown(args[0]))

        return self.dispatch(command, args[1:])

    def dispatch ( self, command: Command, args: Sequence[str] ) -> int:

        if HELP & set(args): return self.say(self.usage(command))

        try: values = self.parse(command, args)
        except Fault as fault: return self.refuse(f"{fault.message}\n\n{self.usage(command)}")

        try: return self.perform(command, values)
        except Fault as fault:

            self._err.write(f"{command.name}: {fault.reason or fault.code.value}: {fault.message}\n")

            for name, problems in (fault.errors or {}).items(): self._err.write(f"  {name}: {'; '.join(problems)}\n")

            return FAILED

    def perform ( self, command: Command, values: dict[str, Any] ) -> int:

        result = command.run(**values)

        if inspect.iscoroutine(result): result = thread.run(result)

        return int(result or 0)

    def parse ( self, command: Command, args: Sequence[str] ) -> dict[str, Any]:

        parser = Parser(prog=f"{self._name} {command.name}", add_help=False, suggest_on_error=True)

        for item in command.inputs: self.declare(parser, item)

        return dict(vars(parser.parse_args(list(args))))

    def declare ( self, parser: Parser, item: Input ) -> None:

        flags = [item.short] if item.short else []

        if item.place == "flag":

            parser.add_argument(*flags, item.switch(), dest=item.name, action="store_true")

        elif item.place == "option":

            parser.add_argument(*flags, item.switch(), dest=item.name, type=converter(item.kind), default=item.default)

        elif item.required(): parser.add_argument(item.name, type=converter(item.kind))
        else: parser.add_argument(item.name, type=converter(item.kind), nargs="?", default=item.default)

    def unknown ( self, name: str ) -> str:

        guess = string.closest(name, self.names(aliases=True))
        hint  = f" Did you mean '{guess}'?" if guess else ""

        return f"Unknown command '{name}'.{hint} Run '{self._name} help' to list the commands."

    def say ( self, text: str ) -> int:

        self._out.write(f"{text}\n")

        return 0

    def refuse ( self, text: str ) -> int:

        self._err.write(f"{text}\n")

        return USAGE

    def help ( self, name: str | None = None ) -> str:

        command = self.find(name) if name else None

        if command is not None: return self.usage(command)

        rows  = sorted(self._commands.values(), key=lambda item: (item.group, item.name))
        width = max((len(command.usage()) for command in rows), default=0) + 3
        lines = [f"{self._name} {self._version}".strip(), self._about, "", f"Usage: {self._name} <command> [options]"]

        for group, commands in grouped(rows).items():

            lines.extend(["", f"{group}:"])
            lines.extend(f"  {command.usage():<{width}}{command.about}" for command in commands)

        lines.extend(["", f"Run '{self._name} <command> --help' for a command's arguments."])

        return "\n".join(line for index, line in enumerate(lines) if line or index > 1)

    def usage ( self, command: Command ) -> str:

        width = max((len(item.label()) for item in command.inputs), default=0) + 3
        lines = [f"Usage: {self._name} {command.usage()}", "", command.about]

        for title, place in (("Arguments", "argument"), ("Options", "option"), ("Flags", "flag")):

            chosen = [item for item in command.inputs if item.place == place]

            if chosen: lines.extend(["", f"{title}:", *(self.line(item, width) for item in chosen)])

        if command.aliases: lines.extend(["", f"Aliases: {', '.join(command.aliases)}"])
        if command.examples: lines.extend(["", "Examples:", *(f"  {example}" for example in command.examples)])

        return "\n".join(lines)

    def line ( self, item: Input, width: int ) -> str:

        default = "" if item.required() or item.place == "flag" else f" (default: {item.default})"

        return f"  {item.label():<{width}}{item.about}{default}"

    def describe ( self ) -> dict[str, Any]:

        return {
            "name": self._name, "version": self._version, "default": self._default,
            "commands": [command.describe() for command in self._commands.values()],
        }
