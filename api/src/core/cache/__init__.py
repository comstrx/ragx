from .cache import Cache, Hit, MemoryStore, Store
from .redis import RedisStore

cache = Cache()

__all__ = ["Cache", "Hit", "MemoryStore", "RedisStore", "Store", "cache"]
