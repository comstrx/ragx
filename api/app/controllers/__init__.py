from app import services
from .health import HealthController
from .hello import HelloController

health = HealthController(services.health)
hello  = HelloController(services.hello)

__all__ = ["HealthController", "HelloController", "health", "hello"]
