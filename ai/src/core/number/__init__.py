from .vector import UnitVector, Vector
from decimal import Decimal

from .format import Format
from .math import Math
from .money import Money
from .number import Number
from .words import Words

number = Number()

vector = Vector()

__all__ = [
    "Decimal", "Format", "Math", "Money", "Number", "UnitVector", "Vector",
    "Words", "number", "vector",
]
