from collections.abc import Iterable

from core.string import string
from .collection import Collection, Kit

class Array(Kit):

    def of[T] ( self, items: Iterable[T] = () ) -> Collection[T]:

        return Collection(items)

    def to_base64 ( self, items: Iterable[int], url: bool = False ) -> str:

        return string.to_base64(bytes(items), url)

    def from_base64 ( self, text: str, url: bool = False ) -> list[int]:

        return list(string.from_base64(text, url))
