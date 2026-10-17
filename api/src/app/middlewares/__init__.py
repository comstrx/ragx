from app import services
from .authenticate import Authenticate

authenticate = Authenticate(services.auth)

__all__ = ["Authenticate", "authenticate"]
