from datetime import UTC, datetime, timedelta

from core.date import date


class TestDate:

    def test_now_is_aware_and_iso_ends_in_z ( self ) -> None:

        moment = date.now()

        assert moment.tzinfo is UTC
        assert date.iso(moment).endswith("Z")
        assert date.parse(date.iso(moment)) == moment.replace(microsecond=(moment.microsecond // 1000) * 1000)

    def test_naive_moments_are_read_as_utc ( self ) -> None:

        naive = datetime.fromisoformat("2026-10-17T12:00:00")

        assert date.utc(naive).tzinfo is UTC
        assert date.iso(naive) == "2026-10-17T12:00:00.000Z"

    def test_arithmetic_and_bounds ( self ) -> None:

        moment = datetime(2026, 10, 17, 15, 30, tzinfo=UTC)

        assert date.add(moment, days=1, hours=2) == moment + timedelta(days=1, hours=2)
        assert date.start_of_day(moment).hour == 0
        assert date.end_of_day(moment).microsecond == 999999
        assert date.between(moment, date.start_of_day(moment), date.end_of_day(moment))
        assert date.since(moment) > 0
        assert date.from_stamp(0).year == 1970
        assert date.elapsed(date.tick()) >= 0
