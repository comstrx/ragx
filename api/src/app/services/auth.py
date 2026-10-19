from core.database import database
from core.token import token
from app.enums import Role as Roles
from app.enums import TokenKind
from app.events import UserRegistered
from app.exceptions import EmailTaken, InvalidCredentials, TokenRevoked, UnknownUser
from app.models import User
from app.repositories import RoleRepository, TokenRepository, UserRepository
from app.resources import UserResource
from app.utils.cycle import Service
from app.utils.dna import passwords

ACCESS_TTL  = 900
REFRESH_TTL = 2_592_000

class AuthService(Service):

    def __init__ (
        self, users: UserRepository, roles: RoleRepository, tokens: TokenRepository, resource: UserResource,
    ) -> None:

        self._users       = users
        self._roles       = roles
        self._tokens      = tokens
        self._resource    = resource
        self._access_ttl  = ACCESS_TTL
        self._refresh_ttl = REFRESH_TTL

    def configure ( self, access_ttl: int, refresh_ttl: int ) -> None:

        self._access_ttl  = access_ttl
        self._refresh_ttl = refresh_ttl

    async def register ( self, name: str, email: str, password: str ) -> dict[str, object]:

        if await self._users.taken(email): raise EmailTaken(email)

        hashed = await passwords.hash(password)
        user   = await self._users.create({ "name": name, "email": email, "password": hashed })
        role   = await self._roles.ensure(Roles.CLIENT.value, Roles.CLIENT.label())

        await self._users.assign(user.id, role.id)
        await UserRegistered(str(user.id), user.name, user.email).dispatch()

        self.log.info("auth.registered", user=str(user.id))

        return await self.session(user)

    async def login ( self, email: str, password: str ) -> dict[str, object]:

        user  = await self._users.find_by_email(email)
        known = await passwords.verify(password, user.password if user else None)

        if user is None or not known: raise InvalidCredentials
        if user.password and passwords.stale(user.password):
            await self._users.update(user.id, { "password": await passwords.hash(password) })

        self.log.info("auth.login", user=str(user.id))

        return await self.session(user)

    async def refresh ( self, refresh_token: str ) -> dict[str, object]:

        claims = token.verify(refresh_token, kind=TokenKind.REFRESH.value)
        stored = await self._tokens.alive(token.fingerprint(refresh_token), TokenKind.REFRESH)

        if stored is None or str(stored.owner_id) != claims.subject: raise TokenRevoked

        async with database.transaction():

            if not await self._tokens.revoke(stored.id): raise TokenRevoked

            return await self.session(await self._users.one(claims.subject))

    async def logout ( self, refresh_token: str, user: User ) -> int:

        stored = await self._tokens.alive(token.fingerprint(refresh_token), TokenKind.REFRESH)

        if stored is None or stored.owner_id != user.id: raise TokenRevoked

        await self._tokens.revoke(stored.id)

        return 1

    async def identify ( self, authorization: str | None ) -> User:

        return await self.bearer(token.bearer(authorization))

    async def bearer ( self, access_token: str | None ) -> User:

        claims = token.verify(access_token or "", kind=TokenKind.ACCESS.value)
        user   = await self._users.with_roles(claims.subject)

        if user is None: raise UnknownUser

        return user

    async def me ( self, user: User ) -> dict[str, object]:

        return self._resource.one(user if "roles" in user.related else await self._users.one(user.id, "roles"))

    async def session ( self, user: User ) -> dict[str, object]:

        whole           = await self._users.one(user.id, "roles")
        subject         = str(whole.id)
        access, _       = token.issue(subject, TokenKind.ACCESS.value, self._access_ttl, roles=whole.role_names())
        refresh, claims = token.issue(subject, TokenKind.REFRESH.value, self._refresh_ttl)

        await self._tokens.remember(whole, TokenKind.REFRESH, token.fingerprint(refresh), claims.expires)

        return {
            "token_type"    : "bearer",
            "access_token"  : access,
            "expires_in"    : self._access_ttl,
            "refresh_token" : refresh,
            "user"          : self._resource.one(whole),
        }
