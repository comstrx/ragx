from core.error import Code, Fault

class InvalidCredentials(Fault):

    def __init__ ( self ) -> None:
        super().__init__(Code.UNAUTHORIZED, reason="credentials")

class TokenRevoked(Fault):

    def __init__ ( self ) -> None:
        super().__init__(Code.UNAUTHORIZED, reason="token.revoked")

class UnknownUser(Fault):

    def __init__ ( self ) -> None:
        super().__init__(Code.UNAUTHORIZED, reason="user")

class EmailTaken(Fault):

    def __init__ ( self, email: str ) -> None:
        super().__init__(Code.CONFLICT, reason="email", errors={ "email": [f"{email} is already registered"] })
