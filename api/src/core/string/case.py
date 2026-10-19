from collections.abc import Mapping

import re

WORDS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|\d+")
SMALL = frozenset({"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "up"})
HOLE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}")

class Case:

    def words ( self, text: str ) -> list[str]:

        return [word.lower() for word in WORDS.findall(text.replace("_", " ").replace("-", " "))]

    def snake ( self, text: str ) -> str:

        return "_".join(self.words(text))

    def kebab ( self, text: str ) -> str:

        return "-".join(self.words(text))

    def studly ( self, text: str ) -> str:

        return "".join(word.capitalize() for word in self.words(text))

    def camel ( self, text: str ) -> str:

        studly = self.studly(text)

        return studly[:1].lower() + studly[1:]

    def title ( self, text: str ) -> str:

        return " ".join(word.capitalize() for word in self.words(text))

    def headline ( self, text: str ) -> str:

        words = self.words(text)

        return " ".join(
            word.capitalize() if index in (0, len(words) - 1) or word not in SMALL else word
            for index, word in enumerate(words)
        )

    def sentence ( self, text: str ) -> str:

        words = self.words(text)

        return " ".join([words[0].capitalize(), *words[1:]]) if words else ""

    def constant ( self, text: str ) -> str:

        return "_".join(word.upper() for word in self.words(text))

    def dotted ( self, text: str ) -> str:

        return ".".join(self.words(text))

    def upper_first ( self, text: str ) -> str:

        return text[:1].upper() + text[1:]

    def lower_first ( self, text: str ) -> str:

        return text[:1].lower() + text[1:]

    def swap ( self, text: str ) -> str:

        return text.swapcase()

    def is_upper ( self, text: str ) -> bool:

        return text.isupper()

    def is_lower ( self, text: str ) -> bool:

        return text.islower()

    def is_snake ( self, text: str ) -> bool:

        return text == self.snake(text)

    def is_kebab ( self, text: str ) -> bool:

        return text == self.kebab(text)

    def is_studly ( self, text: str ) -> bool:

        return text == self.studly(text)

    def is_camel ( self, text: str ) -> bool:

        return text == self.camel(text)

class Template:

    def fill ( self, text: str, data: Mapping[str, object] | None = None, **extra: object ) -> str:

        values = { **(data or {}), **extra }

        def swap ( found: re.Match[str] ) -> str:

            key = found.group(1)

            if key in values: return str(values[key])

            current: object = values

            for part in key.split("."):

                if isinstance(current, Mapping) and part in current: current = current[part]
                else: return found.group(0)

            return str(current)

        return HOLE.sub(swap, text)

    def holes ( self, text: str ) -> list[str]:

        return list(dict.fromkeys(HOLE.findall(text)))

    def has_holes ( self, text: str ) -> bool:

        return HOLE.search(text) is not None

    def table ( self, rows: list[Mapping[str, object]], columns: list[str] | None = None ) -> str:

        if not rows: return ""

        names  = columns or list(rows[0])
        cells  = [[str(row.get(name, "")) for name in names] for row in rows]
        widths = [max(len(name), *(len(line[index]) for line in cells)) for index, name in enumerate(names)]

        def line ( parts: list[str] ) -> str:

            return "  ".join(part.ljust(widths[index]) for index, part in enumerate(parts)).rstrip()

        return "\n".join([line(names), line(["-" * width for width in widths]), *(line(row) for row in cells)])

    def bullets ( self, items: list[object], mark: str = "-" ) -> str:

        return "\n".join(f"{mark} {item}" for item in items)
