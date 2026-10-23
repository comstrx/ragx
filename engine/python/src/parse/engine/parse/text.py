from collections.abc import Iterable
from typing import Any

from engine.error import Code, Fault
import csv, io, re

SEMVER  = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$")
RANGE   = re.compile(r"^\s*(-?\d+)\s*(?:-\s*(-?\d+))?\s*$")
TRIPLE  = 3

class Text:

    def key_values ( self, text: str, separator: str = ",", assign: str = "=" ) -> dict[str, str]:

        found: dict[str, str] = {}

        for piece in text.split(separator):

            if assign not in piece: continue

            key, _, value = piece.partition(assign)

            if key.strip(): found[key.strip()] = value.strip()

        return found

    def csv_line ( self, text: str, delimiter: str = "," ) -> list[str]:

        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter, skipinitialspace=True))

        return [cell.strip() for cell in rows[0]] if rows else []

    def csv_rows ( self, text: str, delimiter: str = "," ) -> list[list[str]]:

        reader = csv.reader(io.StringIO(text), delimiter=delimiter, skipinitialspace=True)

        return [[cell.strip() for cell in row] for row in reader if row]

    def tags ( self, text: str, separator: str = "," ) -> list[str]:

        seen: list[str] = []

        for piece in text.split(separator):

            tag = piece.strip().lower()

            if tag and tag not in seen: seen.append(tag)

        return seen

    def ranges ( self, text: str ) -> list[int]:

        numbers: list[int] = []

        for piece in text.split(","):

            matched = RANGE.match(piece)

            if matched is None: raise Fault(Code.BAD_REQUEST, reason="parse.ranges")

            start = int(matched.group(1))
            end   = int(matched.group(2)) if matched.group(2) is not None else start

            numbers.extend(range(start, end + 1) if end >= start else range(start, end - 1, -1))

        return numbers

    def semver ( self, text: str ) -> dict[str, Any] | None:

        matched = SEMVER.match(text.strip())

        if matched is None: return None

        return {
            "major": int(matched.group(1)), "minor": int(matched.group(2)), "patch": int(matched.group(3)),
            "pre": matched.group(4), "build": matched.group(5),
        }

    def version ( self, text: str ) -> tuple[int, ...]:

        parts = re.findall(r"\d+", text)

        return tuple(int(part) for part in parts[:TRIPLE]) or (0,)

    def compare_versions ( self, left: str, right: str ) -> int:

        first, second = self.version(left), self.version(right)
        width         = max(len(first), len(second))
        first, second = first + (0,) * (width - len(first)), second + (0,) * (width - len(second))

        return (first > second) - (first < second)

    def satisfies ( self, version: str, minimum: str, maximum: str | None = None ) -> bool:

        if self.compare_versions(version, minimum) < 0: return False

        return maximum is None or self.compare_versions(version, maximum) <= 0

    def numbers ( self, text: str ) -> list[float]:

        return [float(found) for found in re.findall(r"-?\d+(?:\.\d+)?", text)]

    def words ( self, text: str ) -> list[str]:

        return re.findall(r"[^\W_]+", text)

    def mentions ( self, text: str, sigil: str = "@" ) -> list[str]:

        return re.findall(rf"(?<!\w){re.escape(sigil)}([\w.-]+)", text)

    def hashtags ( self, text: str ) -> list[str]:

        return self.mentions(text, "#")

    def lines ( self, text: str, keep_blank: bool = False ) -> list[str]:

        return [line.rstrip() for line in text.splitlines() if keep_blank or line.strip()]

    def flags ( self, items: Iterable[str] ) -> dict[str, str | bool]:

        found: dict[str, str | bool] = {}

        for item in items:

            if not item.startswith("--"): continue

            name, _, value = item[2:].partition("=")

            found[name] = value or True

        return found
