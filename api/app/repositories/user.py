from app.enums import Table
from app.models import User
from app.support.bases import BaseRepository


class UserRepository(BaseRepository[User]):

    table = Table.USERS
    model = User

    async def find_by_name ( self, name: str ) -> User | None:
        return await self.find_by(name=name)
