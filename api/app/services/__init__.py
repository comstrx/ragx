from core.database import database
from app.repositories import users
from app.resources import user
from .health import HealthService
from .hello import HelloService

health = HealthService(database)
hello  = HelloService(users, user)

__all__ = ["HealthService", "HelloService", "health", "hello"]
