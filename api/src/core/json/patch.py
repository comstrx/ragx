from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from core.error import Code, Fault
import copy, hashlib, orjson

type Operation = Mapping[str, Any]

SECRET = ("password", "secret", "token", "key", "authorization", "cookie", "credential")
MASK   = "***"

def unescape ( part: str ) -> str:
    return part.replace("~1", "/").replace("~0", "~")

def escape ( part: str ) -> str:
    return part.replace("~", "~0").replace("/", "~1")

def tokens ( pointer: str ) -> list[str]:

    if pointer == "": return []
    if not pointer.startswith("/"): raise Fault(Code.BAD_REQUEST, reason="pointer")

    return [unescape(part) for part in pointer.split("/")[1:]]

def step ( node: Any, part: str ) -> Any:

    if isinstance(node, Mapping):

        if part not in node: raise Fault(Code.NOT_FOUND, reason=f"pointer.{part}")

        return node[part]

    if isinstance(node, list):

        try: return node[int(part)]
        except (ValueError, IndexError) as error: raise Fault(Code.NOT_FOUND, reason=f"pointer.{part}") from error

    raise Fault(Code.NOT_FOUND, reason=f"pointer.{part}")

class Patch:

    def pointer ( self, value: Any, pointer: str, default: Any = None ) -> Any:

        node = value

        try:
            for part in tokens(pointer): node = step(node, part)
        except Fault: return default

        return node

    def has_pointer ( self, value: Any, pointer: str ) -> bool:

        try:
            for part in tokens(pointer): value = step(value, part)
        except Fault: return False

        return True

    def pointer_of ( self, *parts: str | int ) -> str:
        return "".join(f"/{escape(str(part))}" for part in parts)

    def apply ( self, value: Any, operations: Iterable[Operation] ) -> Any:

        document = copy.deepcopy(value)

        for operation in operations: document = self.operate(document, operation)

        return document

    def operate ( self, document: Any, operation: Operation ) -> Any:

        kind = str(operation.get("op", ""))
        path = str(operation.get("path", ""))

        match kind:
            case "add": return self.place(document, path, operation.get("value"), insert=True)
            case "replace":

                if not self.has_pointer(document, path): raise Fault(Code.NOT_FOUND, reason=f"patch.{path}")

                return self.place(document, path, operation.get("value"), insert=False)

            case "remove": return self.drop(document, path)
            case "move":

                moved = self.pointer(document, str(operation.get("from", "")))

                return self.place(self.drop(document, str(operation.get("from", ""))), path, moved, insert=True)

            case "copy":

                cloned = copy.deepcopy(self.pointer(document, str(operation.get("from", ""))))

                return self.place(document, path, cloned, insert=True)

            case "test":

                if self.pointer(document, path, MISSING) != operation.get("value"):
                    raise Fault(Code.CONFLICT, reason=f"patch.{path}")

                return document

            case _: raise Fault(Code.BAD_REQUEST, reason=f"patch.{kind or 'op'}")

    def place ( self, document: Any, path: str, value: Any, insert: bool ) -> Any:

        parts = tokens(path)

        if not parts: return value

        parent = document

        for part in parts[:-1]: parent = step(parent, part)

        last = parts[-1]

        if isinstance(parent, list):

            index = len(parent) if last == "-" else int(last)

            if insert: parent.insert(index, value)
            else: parent[index] = value

        elif isinstance(parent, dict): parent[last] = value
        else: raise Fault(Code.BAD_REQUEST, reason=f"patch.{path}")

        return document

    def drop ( self, document: Any, path: str ) -> Any:

        parts = tokens(path)

        if not parts: return None

        parent = document

        for part in parts[:-1]: parent = step(parent, part)

        last = parts[-1]

        if isinstance(parent, list): parent.pop(int(last))
        elif isinstance(parent, dict) and last in parent: del parent[last]
        else: raise Fault(Code.NOT_FOUND, reason=f"patch.{path}")

        return document

    def changes ( self, before: Any, after: Any, prefix: str = "" ) -> list[dict[str, Any]]:

        if isinstance(before, Mapping) and isinstance(after, Mapping):

            found: list[dict[str, Any]] = []

            for key in sorted(set(before) | set(after), key=str):

                path = f"{prefix}/{escape(str(key))}"

                if key not in after: found.append({ "op": "remove", "path": path })
                elif key not in before: found.append({ "op": "add", "path": path, "value": after[key] })
                else: found.extend(self.changes(before[key], after[key], path))

            return found

        if before == after: return []

        return [{ "op": "replace", "path": prefix or "", "value": after }]

    def checksum ( self, value: Any, size: int = 16 ) -> str:
        return hashlib.blake2b(orjson.dumps(value, option=orjson.OPT_SORT_KEYS), digest_size=size).hexdigest()

    def same ( self, left: Any, right: Any ) -> bool:
        return self.checksum(left) == self.checksum(right)

    def redact ( self, value: Any, keys: Sequence[str] = SECRET, mask: str = MASK ) -> Any:

        if isinstance(value, Mapping):
            return {
                str(key): mask if any(hint in str(key).lower() for hint in keys) else self.redact(item, keys, mask)
                for key, item in value.items()
            }

        if isinstance(value, list): return [self.redact(item, keys, mask) for item in value]

        return value

    def size ( self, value: Any ) -> int:
        return len(orjson.dumps(value))

MISSING = object()
