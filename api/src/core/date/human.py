from datetime import datetime

MINUTE = 60
HOUR   = 3600
DAY    = 86400
WEEK   = 604800
MONTH  = 2629800
YEAR   = 31557600
STEPS  = (
    (YEAR, "year"), (MONTH, "month"), (WEEK, "week"), (DAY, "day"), (HOUR, "hour"), (MINUTE, "minute"),
    (1, "second"),
)
JUST   = 5
NOON   = 12
DUAL   = 2
FEW    = 10
SEVEN  = 7
ARABIC = {
    "second" : ("ثانية", "ثانيتين", "ثوانٍ", "ثانية"),
    "minute" : ("دقيقة", "دقيقتين", "دقائق", "دقيقة"),
    "hour"   : ("ساعة", "ساعتين", "ساعات", "ساعة"),
    "day"    : ("يوم", "يومين", "أيام", "يومًا"),
    "week"   : ("أسبوع", "أسبوعين", "أسابيع", "أسبوعًا"),
    "month"  : ("شهر", "شهرين", "أشهر", "شهرًا"),
    "year"   : ("سنة", "سنتين", "سنوات", "سنة"),
}
DAYS   = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ar": ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"),
}
MONTHS = {
    "en": (
        "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
        "December",
    ),
    "ar": (
        "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
    ),
}
WORDS  = {
    "en": { "now": "just now", "ago": "{} ago", "in": "in {}", "today": "Today", "tomorrow": "Tomorrow",
            "yesterday": "Yesterday", "last": "Last {}", "at": "{} at {}", "am": "AM", "pm": "PM" },
    "ar": { "now": "الآن", "ago": "منذ {}", "in": "بعد {}", "today": "اليوم", "tomorrow": "غدًا",
            "yesterday": "أمس", "last": "{} الماضي", "at": "{} الساعة {}", "am": "ص", "pm": "م" },
}

def chosen ( locale: str ) -> str:

    return locale if locale in WORDS else "en"

def counted ( count: int, unit: str, locale: str, short: bool ) -> str:

    if chosen(locale) == "ar":

        one, two, few, many = ARABIC[unit]

        if count == 1: return one
        if count == DUAL: return two

        return f"{count} {few if count <= FEW else many}"

    if short: return f"{count}{unit[0]}"

    return f"{count} {unit}{'' if count == 1 else 's'}"

class Human:

    def relative ( self, seconds: float, short: bool = False, locale: str = "en", absolute: bool = False ) -> str:

        words    = WORDS[chosen(locale)]
        distance = abs(seconds)

        if distance < JUST: return words["now"]

        size, unit = next((step for step in STEPS if distance >= step[0]), STEPS[-1])
        label      = counted(int(distance // size), unit, locale, short)

        if absolute: return label

        return words["ago"].format(label) if seconds < 0 else words["in"].format(label)

    def span ( self, seconds: float, short: bool = False, locale: str = "en", parts: int = 7 ) -> str:

        left  = int(abs(seconds))
        found: list[str] = []

        for size, unit in STEPS:

            if left < size or unit in ("week", "month") or len(found) >= parts: continue

            count, left = divmod(left, size)

            found.append(counted(count, unit, locale, short))

        joiner = " و" if chosen(locale) == "ar" else " "

        if not found: return "0 ثانية" if chosen(locale) == "ar" else ("0s" if short else "0 seconds")

        return joiner.join(found)

    def clock ( self, moment: datetime, locale: str = "en" ) -> str:

        words = WORDS[chosen(locale)]
        hour  = moment.hour % NOON or NOON
        half  = words["am"] if moment.hour < NOON else words["pm"]

        return f"{hour}:{moment.minute:02d} {half}"

    def calendar ( self, moment: datetime, now: datetime, locale: str = "en" ) -> str:

        words = WORDS[chosen(locale)]
        days  = (moment.date() - now.date()).days
        time  = self.clock(moment, locale)

        if days == 0: day = words["today"]
        elif days == 1: day = words["tomorrow"]
        elif days == -1: day = words["yesterday"]
        elif -SEVEN < days < 0: day = words["last"].format(self.day(moment, locale))
        elif 0 < days < SEVEN: day = self.day(moment, locale)
        else: return moment.strftime("%Y-%m-%d")

        return words["at"].format(day, time)

    def day ( self, moment: datetime, locale: str = "en", short: bool = False ) -> str:

        name = DAYS[chosen(locale)][moment.weekday()]

        return name[:3] if short and chosen(locale) == "en" else name

    def month ( self, moment: datetime, locale: str = "en", short: bool = False ) -> str:

        name = MONTHS[chosen(locale)][moment.month - 1]

        return name[:3] if short and chosen(locale) == "en" else name

    def locales ( self ) -> list[str]:

        return sorted(WORDS)
