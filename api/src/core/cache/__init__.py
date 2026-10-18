from .cache import Cache, Hit
from .lock import Lock
from .redis import RedisStore
from .store import MemoryStore, Store
from .tags import Tagged

cache = Cache()

__all__ = ["Cache", "Hit", "Lock", "MemoryStore", "RedisStore", "Store", "Tagged", "cache"]
