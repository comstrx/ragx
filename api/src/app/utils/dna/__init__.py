from .identity import Identity
from .passwords import Passwords
from .timestamps import Timestamps

identity   = Identity()
passwords  = Passwords()
timestamps = Timestamps()

__all__ = ["Identity", "Passwords", "Timestamps", "identity", "passwords", "timestamps"]
