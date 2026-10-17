from core.database import database
from app.repositories import roles, tokens, users
from app.resources import user
from .auth import AuthService
from .files import FilesService
from .health import HealthService
from .hello import HelloService

auth   = AuthService(users, roles, tokens, user)
files  = FilesService()
health = HealthService(database)
hello  = HelloService(users, user)

__all__ = ["AuthService", "FilesService", "HealthService", "HelloService", "auth", "files", "health", "hello"]
