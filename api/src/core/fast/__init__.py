from .fast import Fast, Sliding, Verdict, Window
from .lru import Lru
from .ttl import Ttl

fast = Fast()

__all__ = ["Fast", "Lru", "Sliding", "Ttl", "Verdict", "Window", "fast"]
