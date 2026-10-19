from .fast import Fast
from .lru import Lru
from .rate import Sliding, Verdict, Window
from .ttl import Ttl

fast = Fast()

__all__ = ["Fast", "Lru", "Sliding", "Ttl", "Verdict", "Window", "fast"]
