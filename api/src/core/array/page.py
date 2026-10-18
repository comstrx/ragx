from collections.abc import Sequence
from typing import TypedDict

class Page(TypedDict):

    page  : int
    limit : int
    total : int
    pages : int

class Pager:

    def page ( self, total: int, page: int = 1, limit: int = 20 ) -> Page:

        limit = max(limit, 1)
        pages = max(-(-total // limit), 1)

        return { "page": min(max(page, 1), pages), "limit": limit, "total": total, "pages": pages }

    def slice[T] ( self, items: Sequence[T], page: int = 1, limit: int = 20 ) -> tuple[list[T], Page]:

        meta  = self.page(len(items), page, limit)
        start = (meta["page"] - 1) * meta["limit"]

        return list(items[start : start + meta["limit"]]), meta

    def offset ( self, page: int = 1, limit: int = 20 ) -> int:
        return (max(page, 1) - 1) * max(limit, 1)

    def has_next ( self, meta: Page ) -> bool:
        return meta["page"] < meta["pages"]

    def has_previous ( self, meta: Page ) -> bool:
        return meta["page"] > 1

    def bounds ( self, meta: Page ) -> tuple[int, int]:

        if meta["total"] == 0: return 0, 0

        start = (meta["page"] - 1) * meta["limit"] + 1

        return start, min(start + meta["limit"] - 1, meta["total"])
