from core.date import date


class SoftDeletes:

    column = "deleted_at"

    def alive ( self, where: dict[str, object] | None = None ) -> dict[str, object]:
        return { **(where or {}), self.column: None }

    def mark ( self ) -> dict[str, object]:
        return { self.column: date.now() }

    def gone ( self, row: dict[str, object] ) -> bool:
        return row.get(self.column) is not None
