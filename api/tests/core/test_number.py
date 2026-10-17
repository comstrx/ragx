from core.number import number


class TestNumber:

    def test_clamp_between_ratio_percent ( self ) -> None:

        assert number.clamp(15, 0, 10) == 10
        assert number.clamp(-1, 0, 10) == 0
        assert number.between(5, 1, 5)
        assert number.ratio(1, 0, default=-1) == -1
        assert number.percent(1, 3) == 33.33

    def test_round_is_half_up_not_bankers ( self ) -> None:

        assert number.round(2.675, 2) == 2.68
        assert number.round(0.5, 0) == 1

    def test_conversions_fall_back ( self ) -> None:

        assert number.to_int(" 42 ") == 42
        assert number.to_int("x", default=7) == 7
        assert number.to_float("1.5") == 1.5
        assert number.to_float(None) == 0.0

    def test_human_sizes ( self ) -> None:

        assert number.human(950) == "950"
        assert number.human(1500) == "1.5K"
        assert number.human(-2_300_000) == "-2.3M"
