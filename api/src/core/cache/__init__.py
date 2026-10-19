from .cache import Cache, Hit, Tagged
from .lock import Lock
from .redis import RedisStore
from .store import MemoryStore, Store

cache = Cache()

__all__ = ["Cache", "Hit", "Lock", "MemoryStore", "RedisStore", "Store", "Tagged", "cache"]
