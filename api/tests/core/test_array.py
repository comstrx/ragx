from core.array import array
import pytest


class TestArray:

    def test_chunk_unique_flatten_compact ( self ) -> None:

        assert array.chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
        assert array.unique([3, 1, 3, 2, 1]) == [3, 1, 2]
        assert array.unique([{"id": 1}, {"id": 1}, {"id": 2}], key=lambda row: row["id"]) == [{"id": 1}, {"id": 2}]
        assert array.flatten([[1], [2, 3], []]) == [1, 2, 3]
        assert array.compact([1, None, 2, None]) == [1, 2]

        with pytest.raises(ValueError, match="0"): array.chunk([1], 0)

    def test_pluck_group_index_partition ( self ) -> None:

        rows = [{"id": 1, "kind": "a"}, {"id": 2, "kind": "b"}, {"id": 3, "kind": "a"}]

        assert array.pluck(rows, "id") == [1, 2, 3]
        assert array.group(rows, lambda row: row["kind"]) == {"a": [rows[0], rows[2]], "b": [rows[1]]}
        assert array.index(rows, lambda row: row["id"])[2] == rows[1]
        assert array.partition([1, 2, 3, 4], lambda n: n % 2 == 0) == ([2, 4], [1, 3])

    def test_first_last_windows ( self ) -> None:

        assert array.first([]) is None
        assert array.first([], default=0) == 0
        assert array.last([1, 2]) == 2
        assert list(array.windows([1, 2, 3], 2)) == [[1, 2], [2, 3]]

    def test_pages_clamp_and_slice ( self ) -> None:

        assert array.page(0) == {"page": 1, "limit": 20, "total": 0, "pages": 1}
        assert array.page(45, page=9, limit=20) == {"page": 3, "limit": 20, "total": 45, "pages": 3}
        assert array.slice(list(range(10)), page=2, limit=4) == (
            [4, 5, 6, 7], {"page": 2, "limit": 4, "total": 10, "pages": 3},
        )
        assert array.offset(3, 20) == 40
