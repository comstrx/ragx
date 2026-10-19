from collections.abc import Mapping
import re

HOLE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}")

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
