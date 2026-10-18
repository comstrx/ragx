from collections.abc import Iterable

from core.string import string
from .collect import Collect
from .dicts import Dicts
from .page import Pager
from .query import Query
from .sets import Sets

class Array(Collect, Dicts, Sets, Pager, Query):

    def to_base64 ( self, items: Iterable[int], url: bool = False ) -> str:
        return string.to_base64(bytes(items), url)

    def from_base64 ( self, text: str, url: bool = False ) -> list[int]:
        return list(string.from_base64(text, url))
