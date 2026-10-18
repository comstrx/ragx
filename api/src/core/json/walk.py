from collections.abc import Mapping, MutableMapping
from typing import Any

MISSING = object()

class Walk:

    def flatten ( self, value: Mapping[str, Any], separator: str = ".", prefix: str = "" ) -> dict[str, Any]:

        flat: dict[str, Any] = {}

        for key, item in value.items():

            path = f"{prefix}{separator}{key}" if prefix else str(key)

            if isinstance(item, Mapping) and item: flat.update(self.flatten(item, separator, path))
            else: flat[path] = item

        return flat

    def unflatten ( self, flat: Mapping[str, Any], separator: str = "." ) -> dict[str, Any]:

        nested: dict[str, Any] = {}

        for path, item in flat.items(): self.put(nested, str(path), item, separator)

        return nested

    def dig ( self, value: object, path: str, default: object = None, separator: str = "." ) -> Any:

        current: object = value

        for part in path.split(separator):

            if isinstance(current, Mapping) and part in current: current = current[part]
            elif isinstance(current, list) and part.lstrip("-").isdigit() and -len(current) <= int(part) < len(current):
                current = current[int(part)]
            else: return default

        return current

    def has ( self, value: object, path: str, separator: str = "." ) -> bool:
        return self.dig(value, path, MISSING, separator) is not MISSING

    def put ( self, value: MutableMapping[str, Any], path: str, item: object, separator: str = "." ) -> None:

        parts   = path.split(separator)
        current = value

        for part in parts[:-1]:

            branch = current.get(part)

            if not isinstance(branch, MutableMapping): branch = current[part] = {}

            current = branch

        current[parts[-1]] = item

    def forget ( self, value: MutableMapping[str, Any], path: str, separator: str = "." ) -> bool:

        parts  = path.split(separator)
        parent = self.dig(value, separator.join(parts[:-1]), value, separator) if len(parts) > 1 else value

        if isinstance(parent, MutableMapping) and parts[-1] in parent:

            del parent[parts[-1]]

            return True

        return False

    def merge ( self, base: Mapping[str, Any], *layers: Mapping[str, Any], lists: str = "replace" ) -> dict[str, Any]:

        merged: dict[str, Any] = dict(base)

        for layer in layers:

            for key, item in layer.items():

                known = merged.get(key)

                if isinstance(known, Mapping) and isinstance(item, Mapping):
                    merged[key] = self.merge(known, item, lists=lists)
                elif isinstance(known, list) and isinstance(item, list) and lists == "append":
                    merged[key] = [*known, *item]
                else: merged[key] = item

        return merged

    def diff ( self, before: Mapping[str, Any], after: Mapping[str, Any] ) -> dict[str, tuple[Any, Any]]:

        flat_before = self.flatten(before)
        flat_after  = self.flatten(after)
        changed: dict[str, tuple[Any, Any]] = {}

        for key in sorted(set(flat_before) | set(flat_after)):

            old = flat_before.get(key, MISSING)
            new = flat_after.get(key, MISSING)

            if old != new: changed[key] = (None if old is MISSING else old, None if new is MISSING else new)

        return changed

    def only ( self, value: Mapping[str, Any], *paths: str ) -> dict[str, Any]:

        picked: dict[str, Any] = {}

        for path in paths:

            found = self.dig(value, path, MISSING)

            if found is not MISSING: self.put(picked, path, found)

        return picked

    def prune ( self, value: Any, empty: tuple[object, ...] = (None,) ) -> Any:

        if isinstance(value, Mapping):

            kept = { key: self.prune(item, empty) for key, item in value.items() }

            return { key: item for key, item in kept.items() if item not in empty }

        if isinstance(value, list): return [self.prune(item, empty) for item in value if item not in empty]

        return value
