from core.string import string
import pytest


class TestString:

    def test_cases_split_words_the_same_way ( self ) -> None:

        assert string.snake("HelloBigWorld") == "hello_big_world"
        assert string.kebab("hello_big_world") == "hello-big-world"
        assert string.studly("hello-big world") == "HelloBigWorld"
        assert string.camel("hello big world") == "helloBigWorld"
        assert string.title("hello_big-world") == "Hello Big World"

    def test_slug_strips_accents_and_symbols ( self ) -> None:

        assert string.slug("Café — RagX 2.0!") == "cafe-ragx-2-0"
        assert string.slug("  spaced   out  ", "_") == "spaced_out"

    def test_truncate_and_mask_keep_their_promises ( self ) -> None:

        assert string.truncate("hello world", 8) == "hello w…"
        assert string.truncate("short", 8) == "short"
        assert string.mask("4111111111111111") == "************1111"
        assert string.mask("abc", keep=4) == "***"

    def test_random_and_token_are_unpredictable_and_sized ( self ) -> None:

        assert len(string.random(24)) == 24
        assert string.random() != string.random()
        assert len(string.token()) >= 32

    def test_hash_is_stable_and_refuses_weak_algorithms ( self ) -> None:

        assert string.hash("ragx") == string.hash("ragx")
        assert len(string.hash("ragx")) == 64

        with pytest.raises(ValueError, match="md5"): string.hash("ragx", "md5")

    def test_join_plural_and_predicates ( self ) -> None:

        assert string.join(["a", None, "b", ""], final=" and ") == "a and b"
        assert string.plural("box") == "boxes"
        assert string.plural("city") == "cities"
        assert string.plural("cat", 1) == "cat"
        assert string.is_email("a@b.co")
        assert not string.is_email("a@b")
        assert string.is_url("https://ragx.test/x?y=1")
        assert string.is_blank("  ")
        assert string.collapse("  a \n b  ") == "a b"
