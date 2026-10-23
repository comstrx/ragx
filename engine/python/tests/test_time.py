from datetime import UTC, datetime, timedelta

from engine.date import Duration, Moment, Period, clock, date
from engine.error import Code
from engine.test import expect, test

MONDAY = Moment.of(2026, 10, 19, 9, 30)

class TestMoments:

    def test_calendar_navigation_matches_carbon ( self ) -> None:

        expect((MONDAY.day_name(), MONDAY.month_name(short=True), MONDAY.is_business_day())).equals(
            ("Monday", "Oct", True),
        )
        expect((MONDAY.add_business_days(5).to_date_string(), MONDAY.add_business_days(-1).day_name())).equals(
            ("2026-10-26", "Friday"),
        )
        expect((MONDAY.business_days_until(MONDAY.add(days=7)), MONDAY.next("friday").day())).equals((5, 23))
        expect((MONDAY.previous("monday").day(), MONDAY.next("monday").day(), MONDAY.week_of_month())).equals(
            (12, 26, 4),
        )
        expect((MONDAY.first_of_month("thursday").day(), MONDAY.last_of_month("saturday").day())).equals((1, 31))
        expect((MONDAY.nth_of_month(5, "sunday"), Moment.of(2026, 10, 31).is_last_of_month())).equals((None, True))
        expect((MONDAY.set(hour=12).hour(), MONDAY.floor("hour").minute(), MONDAY.round("hour").hour())).equals(
            (12, 0, 10),
        )
        expect((MONDAY.ceil("hour").hour(), MONDAY.to_datetime_string(), MONDAY.calendar_week())).equals(
            (10, "2026-10-19 09:30:00", (2026, 43)),
        )
        expect((
            Moment.of(2000, 2, 29).age(Moment.of(2026, 2, 28)), Moment.of(2000, 2, 29).age(Moment.of(2026, 3, 1)),
        )).equals(
            (25, 26),
        )
        expect((date.is_leap(2024), date.is_leap(2100), date.days_in(2026, 2), "Africa/Cairo" in date.zones())).equals(
            (True, False, 28, True),
        )
        expect((MONDAY.add(months=1, days=-19).date(), Moment.of(2026, 1, 31).add(months=1).date())).equals(
            ("2026-10-31", "2026-02-28"),
        )
        expect((MONDAY.start_of("quarter").date(), MONDAY.end_of("quarter").iso())).equals(
            ("2026-10-01", "2026-12-31T23:59:59.999Z"),
        )
        expect((MONDAY.end_of("month").date(), MONDAY.end_of("week").date(), MONDAY.end_of("year").date())).equals(
            ("2026-10-31", "2026-10-25", "2026-12-31"),
        )

        with test.fails(Code.BAD_REQUEST, "date.unit"): MONDAY.start_of("fortnight")
        with test.fails(Code.BAD_REQUEST, "date.shift"): MONDAY.add(decades=1)
        with test.fails(Code.BAD_REQUEST, "date.weekday"): MONDAY.next("funday")
        with test.fails(Code.BAD_REQUEST, "date.of"): Moment.of(2026, 2, 30)

    def test_differences_are_calendar_aware ( self ) -> None:

        start = Moment.of(2026, 1, 31, 10)

        expect((
            start.diff_in("month", Moment.of(2026, 2, 28, 10)), start.diff_in("month", Moment.of(2026, 3, 31, 10)),
        )).equals(
            (0, 2),
        )
        expect((
            start.diff_in("year", Moment.of(2027, 1, 31, 9)), start.diff_in("year", Moment.of(2027, 1, 31, 10)),
        )).equals(
            (0, 1),
        )
        expect((
            start.diff_in("day", start.sub(days=3), absolute=False), start.diff_in("hour", start.add(minutes=150)),
        )).equals(
            (-3, 2),
        )
        expect((start.diff_in("quarter", start.add(months=7)), start.diff_in("week", start.add(days=20)))).equals(
            (2, 2),
        )
        expect((start.is_birthday(Moment.of(2030, 1, 31)), start.average(start.add(hours=4)).hour())).equals((True, 12))
        expect((start.closest(MONDAY, start.add(days=1)), start.farthest(MONDAY, start.add(days=1)))).equals(
            (start.add(days=1), MONDAY),
        )
        expect((
            start.is_same(start.to("Asia/Riyadh"), "hour"), start.is_start_of_day(),
            start.start_of("day").is_start_of_day(),
        )).equals(
            (True, False, True),
        )

        with test.fails(Code.BAD_REQUEST, "date.unit"): start.diff_in("century")
        with test.fails(Code.BAD_REQUEST, "date.closest"): start.closest()

    def test_formats_read_and_speak_english_and_arabic ( self ) -> None:

        expect((MONDAY.format("dddd D MMMM YYYY, h:mm A"), MONDAY.format("dddd D MMMM YYYY h:mm A", "ar"))).equals(
            ("Monday 19 October 2026, 9:30 AM", "الاثنين 19 أكتوبر 2026 9:30 ص"),
        )
        expect(MONDAY.format("[Week] W, Do [of] MMM")).equals("Week 43, 19th of Oct")
        expect(Moment.from_format("19/10/2026 14:05", "DD/MM/YYYY HH:mm", "Africa/Cairo").iso()).equals(
            "2026-10-19T11:05:00.000Z",
        )
        expect(Moment.from_format("Oct 5, 2026", "MMM D, YYYY").date()).equals("2026-10-05")

        later = MONDAY.add(minutes=3)

        expect((MONDAY.human(later), later.human(MONDAY), MONDAY.human(later, short=True))).equals(
            ("3 minutes ago", "in 3 minutes", "3m ago"),
        )
        expect((MONDAY.human(MONDAY.add(seconds=2)), MONDAY.human(later, absolute=True))).equals(
            ("just now", "3 minutes"),
        )
        expect((MONDAY.human(later, locale="ar"), MONDAY.human(MONDAY.add(days=2), locale="ar"))).equals(
            ("منذ 3 دقائق", "منذ يومين"),
        )
        expect((MONDAY.add(hours=1).human(MONDAY, locale="ar"), MONDAY.human(MONDAY.add(days=15), locale="ar"))).equals(
            ("بعد ساعة", "منذ أسبوعين"),
        )
        expect((
            MONDAY.human(MONDAY.add(hours=13), locale="ar"), MONDAY.human(MONDAY.add(days=12), locale="ar"),
        )).equals(
            ("منذ 13 ساعة", "منذ أسبوع"),
        )
        expect((
            MONDAY.calendar(MONDAY.add(hours=2)), MONDAY.calendar(MONDAY.add(days=1)),
            MONDAY.calendar(MONDAY.sub(days=1)),
        )).equals(
            ("Today at 9:30 AM", "Yesterday at 9:30 AM", "Tomorrow at 9:30 AM"),
        )
        expect((MONDAY.calendar(MONDAY.add(days=3), "ar"), MONDAY.calendar(MONDAY.add(days=30)))).equals(
            ("الاثنين الماضي الساعة 9:30 ص", "2026-10-19"),
        )
        expect((date.span(3725), date.span(3725, short=True), date.span(3725, locale="ar"))).equals(
            ("1 hour 2 minutes 5 seconds", "1h 2m 5s", "ساعة ودقيقتين و5 ثوانٍ"),
        )

        with test.fails(Code.BAD_REQUEST, "date.format"): Moment.from_format("2026-99-99", "YYYY-MM-DD")
        with test.fails(Code.BAD_REQUEST, "date.token"): Moment.from_format("1", "Q")

    def test_the_clock_freezes_travels_and_thaws_for_brutal_tests ( self ) -> None:

        with date.frozen("2026-05-01 08:00") as frozen:

            expect((frozen.iso(), Moment.now().iso(), date.now().isoformat())).equals(
                ("2026-05-01T08:00:00.000Z", "2026-05-01T08:00:00.000Z", "2026-05-01T08:00:00+00:00"),
            )
            expect((date.stamp(), Moment.today().iso(), clock.frozen())).equals(
                (frozen.stamp(), "2026-05-01T00:00:00.000Z", True),
            )

            date.travel(days=2, hours=1)

            expect((Moment.now().iso(), Moment.parse("tomorrow").date(), Moment.of(2026, 5, 3, 9).is_today())).equals(
                ("2026-05-03T09:00:00.000Z", "2026-05-04", True),
            )
            expect((Moment.of(2026, 5, 2).is_yesterday(), Moment.of(2026, 5, 4).is_tomorrow())).equals((True, True))
            expect((Moment.of(2026, 5, 3).is_past(), Moment.of(2026, 5, 4).is_future())).equals((True, True))
            expect(Moment.of(2000, 5, 3).age()).equals(26)

            clock.back(days=1)

            expect(Moment.now().date()).equals("2026-05-02")

        expect(clock.frozen()).false()
        expect(abs(Moment.now().stamp() - datetime.now(UTC).timestamp())).below(5)

    def test_weekends_follow_the_region ( self ) -> None:

        thursday = Moment.of(2026, 10, 22)

        try:

            expect(date.weekend("friday", "saturday")).equals(frozenset({4, 5}))
            expect((thursday.add(days=1).is_weekend(), thursday.add(days=3).is_weekend())).equals((True, False))
            expect((
                thursday.add_business_days(1).day_name(), thursday.business_days_until(thursday.add(days=7)),
            )).equals(
                ("Sunday", 5),
            )

        finally: date.weekend("saturday", "sunday")

        expect(thursday.add_business_days(1).day_name()).equals("Friday")

class TestSpans:

    def test_durations_and_periods_measure_and_split ( self ) -> None:

        expect((
            Duration.of(hours=1, minutes=30).minutes(), Duration.parse("90m").hours(),
            Duration.parse(timedelta(days=1)).days(),
        )).equals(
            (90.0, 1.5, 1.0),
        )
        expect((Duration.of(minutes=1).iso(), Duration(3725).clock(), Duration(-3).abs().total)).equals(
            ("PT1M", "01:02:05", 3.0),
        )

        period = Period.of("2026-10-01", "2026-10-31")

        expect((period.count("day"), len(period.days()), period.contains(MONDAY))).equals((31, 31, True))
        expect([part.start.date() for part in period.split(3)]).equals(["2026-10-01", "2026-10-11", "2026-10-21"])

        with test.fails(Code.BAD_REQUEST, "date.duration"): Duration.of(fortnights=1)
        with test.fails(Code.BAD_REQUEST, "date.duration"): Duration.parse("soon")
        with test.fails(Code.BAD_REQUEST, "date.split"): period.split(0)
