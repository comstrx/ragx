from core.database import Translate, query
from asyncpg import exceptions as pg
import pytest


class TestQuery:

    def test_select_builds_scoped_ordered_pages ( self ) -> None:

        where     = {"deleted_at": None, "role": "client"}
        statement = query.select("users", ("id", "name"), where, ("-created_at", "name"), 20, 40)

        assert statement.sql == (
            'SELECT "id", "name" FROM "users" WHERE "deleted_at" IS NULL AND "role" = $1 '
            'ORDER BY "created_at" DESC, "name" ASC LIMIT $2 OFFSET $3'
        )
        assert statement.params == ("client", 20, 40)

    def test_lists_become_any_and_writes_return_rows ( self ) -> None:

        assert query.select("users", where={"id": [1, 2]}).sql == 'SELECT * FROM "users" WHERE "id" = ANY($1)'
        insert = query.insert("users", {"name": "x", "role": "client"})
        update = query.update("users", {"name": "y"}, {"id": 1}, ("id",))

        assert insert.sql == 'INSERT INTO "users" ("name", "role") VALUES ($1, $2) RETURNING *'
        assert update.sql == 'UPDATE "users" SET "name" = $1 WHERE "id" = $2 RETURNING "id"'
        assert update.params == ("y", 1)
        assert query.delete("users", {"id": 1}).sql == 'DELETE FROM "users" WHERE "id" = $1'
        count = query.count("users", {"deleted_at": None})

        assert count.sql == 'SELECT count(*) FROM "users" WHERE "deleted_at" IS NULL'

    def test_identifiers_are_validated_never_interpolated ( self ) -> None:

        with pytest.raises(ValueError, match="drop"): query.select('users"; drop table users; --')
        with pytest.raises(ValueError, match="Name"): query.select("users", ("Name",))
        with pytest.raises(ValueError, match="users"): query.update("users", {}, {"id": 1})
        with pytest.raises(ValueError, match="users"): query.delete("users", {})

    def test_database_errors_become_faults ( self ) -> None:

        translate = Translate()

        assert translate.fault(pg.UniqueViolationError("dup")).code == "conflict"
        assert translate.fault(pg.ForeignKeyViolationError("fk")).code == "bad_request"
        assert translate.fault(pg.NotNullViolationError("null")).code == "validation"
        assert translate.fault(pg.TooManyConnectionsError("busy")).code == "unavailable"
        assert translate.fault(OSError("refused")).code == "unavailable"
        assert translate.fault(RuntimeError("?")).code == "internal"
