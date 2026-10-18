from decimal import Decimal

from .format import Format
from .math import Math
from .number import Number
from .words import Words

number = Number()

__all__ = ["Decimal", "Format", "Math", "Number", "Words", "number"]
