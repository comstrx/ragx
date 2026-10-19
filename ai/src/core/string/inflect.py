import re

UNCOUNTABLE = frozenset({
    "equipment", "information", "rice", "money", "species", "series", "fish", "sheep", "deer", "news", "data",
    "metadata", "media", "staff", "software", "hardware", "traffic", "feedback", "advice", "luggage", "music",
})
IRREGULAR = {
    "person": "people", "man": "men", "woman": "women", "child": "children", "tooth": "teeth", "foot": "feet",
    "mouse": "mice", "goose": "geese", "ox": "oxen", "leaf": "leaves", "life": "lives", "knife": "knives",
    "wife": "wives", "half": "halves", "self": "selves", "elf": "elves", "loaf": "loaves", "potato": "potatoes",
    "tomato": "tomatoes", "cactus": "cacti", "focus": "foci", "fungus": "fungi", "nucleus": "nuclei",
    "syllabus": "syllabi", "analysis": "analyses", "diagnosis": "diagnoses", "oasis": "oases", "thesis": "theses",
    "crisis": "crises", "phenomenon": "phenomena", "criterion": "criteria", "datum": "data", "medium": "media",
    "index": "indices", "matrix": "matrices", "vertex": "vertices", "appendix": "appendices", "quiz": "quizzes",
    "status": "statuses", "alias": "aliases", "bus": "buses", "campus": "campuses", "virus": "viruses",
}
SINGULAR  = { plural: singular for singular, plural in IRREGULAR.items() }
PLURALS   = (
    (re.compile(r"(quiz)$", re.IGNORECASE), r"\1zes"),
    (re.compile(r"([m|l])ouse$", re.IGNORECASE), r"\1ice"),
    (re.compile(r"(matr|vert|ind|append)(?:ix|ex)$", re.IGNORECASE), r"\1ices"),
    (re.compile(r"(x|ch|ss|sh|z)$", re.IGNORECASE), r"\1es"),
    (re.compile(r"([^aeiouy]|qu)y$", re.IGNORECASE), r"\1ies"),
    (re.compile(r"(hive)$", re.IGNORECASE), r"\1s"),
    (re.compile(r"(?:([^f])fe|([lr])f)$", re.IGNORECASE), r"\1\2ves"),
    (re.compile(r"sis$", re.IGNORECASE), "ses"),
    (re.compile(r"([ti])um$", re.IGNORECASE), r"\1a"),
    (re.compile(r"(buffal|tomat|potat|her)o$", re.IGNORECASE), r"\1oes"),
    (re.compile(r"(bu)s$", re.IGNORECASE), r"\1ses"),
    (re.compile(r"(alias|status)$", re.IGNORECASE), r"\1es"),
    (re.compile(r"(octop|vir)us$", re.IGNORECASE), r"\1i"),
    (re.compile(r"(ax|test)is$", re.IGNORECASE), r"\1es"),
    (re.compile(r"s$", re.IGNORECASE), "s"),
    (re.compile(r"$"), "s"),
)
SINGULARS = (
    (re.compile(r"(quiz)zes$", re.IGNORECASE), r"\1"),
    (re.compile(r"(matr)ices$", re.IGNORECASE), r"\1ix"),
    (re.compile(r"(vert|ind|append)ices$", re.IGNORECASE), r"\1ex"),
    (re.compile(r"([m|l])ice$", re.IGNORECASE), r"\1ouse"),
    (re.compile(r"(x|ch|ss|sh)es$", re.IGNORECASE), r"\1"),
    (re.compile(r"(cris|ax|test)es$", re.IGNORECASE), r"\1is"),
    (re.compile(r"(octop|vir)i$", re.IGNORECASE), r"\1us"),
    (re.compile(r"(alias|status)(es)?$", re.IGNORECASE), r"\1"),
    (re.compile(r"(bu)ses$", re.IGNORECASE), r"\1s"),
    (re.compile(r"([ti])a$", re.IGNORECASE), r"\1um"),
    (re.compile(r"(analy|diagno|parenthe|progno|synop|the)ses$", re.IGNORECASE), r"\1sis"),
    (re.compile(r"([^f])ves$", re.IGNORECASE), r"\1fe"),
    (re.compile(r"(hive)s$", re.IGNORECASE), r"\1"),
    (re.compile(r"(tive)s$", re.IGNORECASE), r"\1"),
    (re.compile(r"([lr])ves$", re.IGNORECASE), r"\1f"),
    (re.compile(r"([^aeiouy]|qu)ies$", re.IGNORECASE), r"\1y"),
    (re.compile(r"(s)eries$", re.IGNORECASE), r"\1eries"),
    (re.compile(r"(m)ovies$", re.IGNORECASE), r"\1ovie"),
    (re.compile(r"(x|ch|ss|sh)es$", re.IGNORECASE), r"\1"),
    (re.compile(r"(o)es$", re.IGNORECASE), r"\1"),
    (re.compile(r"(shoe)s$", re.IGNORECASE), r"\1"),
    (re.compile(r"(cris|ax|test)is$", re.IGNORECASE), r"\1is"),
    (re.compile(r"ss$", re.IGNORECASE), "ss"),
    (re.compile(r"s$", re.IGNORECASE), ""),
)

class Inflect:

    def plural ( self, word: str, count: int = 2 ) -> str:

        if count == 1 or not word: return word

        lower = word.lower()

        if lower in UNCOUNTABLE: return word
        if lower in IRREGULAR: return self.match_case(word, IRREGULAR[lower])

        for pattern, replacement in PLURALS:
            if pattern.search(word): return pattern.sub(replacement, word)

        return word

    def singular ( self, word: str ) -> str:

        if not word: return word

        lower = word.lower()

        if lower in UNCOUNTABLE: return word
        if lower in SINGULAR: return self.match_case(word, SINGULAR[lower])

        for pattern, replacement in SINGULARS:
            if pattern.search(word): return pattern.sub(replacement, word)

        return word

    def choose ( self, word: str, count: int ) -> str:

        one, bar, many = word.partition("|")

        if bar: return one if count == 1 else many

        return self.plural(word, count)

    def counted ( self, word: str, count: int ) -> str:

        return f"{count} {self.choose(word, count)}"

    def is_plural ( self, word: str ) -> bool:

        return word.lower() not in UNCOUNTABLE and self.singular(word) != word

    def match_case ( self, source: str, target: str ) -> str:

        if source.isupper(): return target.upper()
        if source[:1].isupper(): return target[:1].upper() + target[1:]

        return target
