from uuid import UUID

from .rand import Rand

Uuid = UUID
rand = Rand()

__all__ = ["Rand", "Uuid", "rand"]
