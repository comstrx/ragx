from uuid import UUID

from core.error import Fault
from core.http import App
from app.enums import Role
from app.repositories import users
from app.resources import user as resource
import pytest


@pytest.mark.anyio
class TestUserRepository:

    async def test_a_user_lives_through_create_find_update_and_soft_delete ( self, app: App ) -> None:

        created = await users.create({ "name": "Ada", "email": "ada@ragx.test", "role": Role.ADMIN })

        try:

            assert created.id.version == 7
            assert created.is_staff()
            assert created.created_at == created.updated_at
            assert await users.find(created.id) == created
            assert await users.find_by_name("Ada") == created
            assert await users.one(str(created.id)) == created

            renamed = await users.update(created.id, { "name": "Ada L." })

            assert renamed.name == "Ada L."
            assert renamed.updated_at > created.updated_at

            found, meta = await users.all(limit=50)

            assert renamed in found
            assert meta["total"] >= 2

        finally: assert await users.delete(created.id)

        assert await users.find(created.id) is None
        assert await users.count({ "name": "Ada L." }) == 0

    async def test_faults_are_unified_at_the_edge_of_the_table ( self, app: App ) -> None:

        with pytest.raises(Fault) as missing: await users.one(UUID(int=1))
        with pytest.raises(Fault) as malformed: await users.find("not-an-id")
        with pytest.raises(Fault) as duplicate: await users.create({ "name": "world" })

        assert missing.value.code == "not_found"
        assert malformed.value.code == "bad_request"
        assert malformed.value.errors == { "id": ["Expected an id"] }
        assert duplicate.value.code == "conflict"
        assert duplicate.value.reason == "users_name_alive"

    async def test_the_resource_exposes_only_public_fields_in_wire_types ( self, app: App ) -> None:

        world = await users.find_by_name("World")

        assert world is not None

        shaped = resource.one(world)

        assert set(shaped) == { "id", "name", "role", "created_at" }
        assert shaped["role"] == "client"
        assert isinstance(shaped["id"], str)
        assert str(shaped["created_at"]).endswith("Z")
