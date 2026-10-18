import re

WORDS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|\d+")
SMALL = frozenset({"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "up"})

class Case:

    def words ( self, text: str ) -> list[str]:
        return [word.lower() for word in WORDS.findall(text.replace("_", " ").replace("-", " "))]

    def snake ( self, text: str ) -> str:
        return "_".join(self.words(text))

    def kebab ( self, text: str ) -> str:
        return "-".join(self.words(text))

    def studly ( self, text: str ) -> str:
        return "".join(word.capitalize() for word in self.words(text))

    def camel ( self, text: str ) -> str:

        studly = self.studly(text)

        return studly[:1].lower() + studly[1:]

    def title ( self, text: str ) -> str:
        return " ".join(word.capitalize() for word in self.words(text))

    def headline ( self, text: str ) -> str:

        words = self.words(text)

        return " ".join(
            word.capitalize() if index in (0, len(words) - 1) or word not in SMALL else word
            for index, word in enumerate(words)
        )

    def sentence ( self, text: str ) -> str:

        words = self.words(text)

        return " ".join([words[0].capitalize(), *words[1:]]) if words else ""

    def constant ( self, text: str ) -> str:
        return "_".join(word.upper() for word in self.words(text))

    def dotted ( self, text: str ) -> str:
        return ".".join(self.words(text))

    def upper_first ( self, text: str ) -> str:
        return text[:1].upper() + text[1:]

    def lower_first ( self, text: str ) -> str:
        return text[:1].lower() + text[1:]

    def swap ( self, text: str ) -> str:
        return text.swapcase()

    def is_upper ( self, text: str ) -> bool:
        return text.isupper()

    def is_lower ( self, text: str ) -> bool:
        return text.islower()

    def is_snake ( self, text: str ) -> bool:
        return text == self.snake(text)

    def is_kebab ( self, text: str ) -> bool:
        return text == self.kebab(text)

    def is_studly ( self, text: str ) -> bool:
        return text == self.studly(text)

    def is_camel ( self, text: str ) -> bool:
        return text == self.camel(text)
