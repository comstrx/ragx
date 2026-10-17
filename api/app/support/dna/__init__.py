from .identity import Identity
from .soft_deletes import SoftDeletes
from .timestamps import Timestamps

identity     = Identity()
soft_deletes = SoftDeletes()
timestamps   = Timestamps()

__all__ = ["Identity", "SoftDeletes", "Timestamps", "identity", "soft_deletes", "timestamps"]
