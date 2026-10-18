import math

ONES   = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
)
TENS   = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
SCALES = ((10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand"), (100, "hundred"))
ROMAN  = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"),
    (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)
TEEN     = 20
TEN      = 10
HUNDRED  = 100
TWO      = 2
THREE    = 3
FOUR     = 4
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

class Words:

    def spell ( self, value: int ) -> str:

        if value < 0: return f"minus {self.spell(-value)}"
        if value < TEEN: return ONES[value]
        if value < HUNDRED:

            tens, ones = divmod(value, TEN)

            return TENS[tens] if ones == 0 else f"{TENS[tens]}-{ONES[ones]}"

        for size, name in SCALES:

            if value >= size:

                head, rest = divmod(value, size)
                spoken     = f"{self.spell(head)} {name}"

                return spoken if rest == 0 else f"{spoken} {self.spell(rest)}"

        return ONES[0]

    def spell_ordinal ( self, value: int ) -> str:

        spoken = self.spell(value)
        last   = spoken.split()[-1].split("-")[-1]
        rules  = {
            "one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
            "twelve": "twelfth",
        }

        if last in rules: tail = rules[last]
        elif last.endswith("y"): tail = f"{last[:-1]}ieth"
        else: tail = f"{last}th"

        return spoken[:len(spoken) - len(last)] + tail

    def from_roman ( self, text: str ) -> int:

        values = { symbol: value for value, symbol in ROMAN if len(symbol) == 1 }
        total  = 0
        upper  = text.upper()

        for index, char in enumerate(upper):

            value = values.get(char)

            if value is None: raise ValueError(text)

            after = values.get(upper[index + 1], 0) if index + 1 < len(upper) else 0

            total += -value if value < after else value

        return total

    def is_prime ( self, value: int ) -> bool:

        if value < TWO: return False
        if value < FOUR: return True
        if value % 2 == 0 or value % THREE == 0: return False

        divisor = 5

        while divisor * divisor <= value:

            if value % divisor == 0 or value % (divisor + 2) == 0: return False

            divisor += 6

        return True

    def factorial ( self, value: int ) -> int:
        return math.factorial(value)

    def digit_sum ( self, value: int ) -> int:
        return sum(int(digit) for digit in str(abs(value)))

    def digits ( self, value: int ) -> list[int]:
        return [int(digit) for digit in str(abs(value))]

    def is_power_of ( self, value: int, base: int ) -> bool:

        if value < 1 or base < TWO: return False

        while value % base == 0: value //= base

        return value == 1

    def next_power_of ( self, value: int, base: int = TWO ) -> int:

        power = 1

        while power < value: power *= base

        return power

    def lerp ( self, start: float, end: float, amount: float ) -> float:
        return start + (end - start) * amount

    def normalize ( self, value: float, low: float, high: float ) -> float:
        return (value - low) / (high - low) if high != low else 0.0

    def map_range ( self, value: float, low: float, high: float, new_low: float, new_high: float ) -> float:
        return new_low + self.normalize(value, low, high) * (new_high - new_low)

    def to_base ( self, value: int, base: int ) -> str:

        if not TWO <= base <= len(ALPHABET): raise ValueError(base)
        if value == 0: return "0"

        sign = "-" if value < 0 else ""
        left = abs(value)
        digits: list[str] = []

        while left:

            left, remainder = divmod(left, base)

            digits.append(ALPHABET[remainder])

        return sign + "".join(reversed(digits))

    def from_base ( self, text: str, base: int ) -> int:
        return int(text, base)
