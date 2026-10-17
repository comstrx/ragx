from .role import RoleRepository
from .token import TokenRepository
from .user import UserRepository

roles  = RoleRepository()
tokens = TokenRepository()
users  = UserRepository()

__all__ = ["RoleRepository", "TokenRepository", "UserRepository", "roles", "tokens", "users"]
