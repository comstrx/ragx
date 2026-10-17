from .roles import RolesSeeder
from .users import UsersSeeder

seeders = (RolesSeeder(), UsersSeeder())

__all__ = ["RolesSeeder", "UsersSeeder", "seeders"]
