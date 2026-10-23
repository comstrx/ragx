from .math import Embedding, Math, Vector
from .money import Money
from .number import Format, Number
from .words import Words
from decimal import Decimal

number = Number()
vector = Vector()

__all__ = ["Decimal", "Embedding", "Format", "Math", "Money", "Number", "Vector", "Words", "number", "vector"]
