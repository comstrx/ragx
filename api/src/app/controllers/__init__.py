from app import services
from .auth import AuthController
from .files import FilesController
from .health import HealthController
from .hello import HelloController

auth   = AuthController(services.auth)
files  = FilesController(services.files)
health = HealthController(services.health)
hello  = HelloController(services.hello)

__all__ = [
    "AuthController", "FilesController", "HealthController", "HelloController", "auth", "files", "health", "hello",
]
