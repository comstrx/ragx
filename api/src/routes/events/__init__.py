from collections.abc import Mapping, Sequence

listeners: Mapping[type, Sequence[type]] = {}

__all__ = ["listeners"]
