from core.database import database
from .user import UserRepository

users = UserRepository(database)

__all__ = ["UserRepository", "users"]
