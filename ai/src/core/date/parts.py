from datetime import datetime

import calendar as months

class Parts:

    at: datetime

    def year ( self ) -> int:

        return self.at.year

    def month ( self ) -> int:

        return self.at.month

    def day ( self ) -> int:

        return self.at.day

    def hour ( self ) -> int:

        return self.at.hour

    def minute ( self ) -> int:

        return self.at.minute

    def second ( self ) -> int:

        return self.at.second

    def weekday ( self ) -> int:

        return self.at.isoweekday()

    def day_of_year ( self ) -> int:

        return self.at.timetuple().tm_yday

    def week ( self ) -> int:

        return self.at.isocalendar().week

    def quarter ( self ) -> int:

        return (self.at.month - 1) // 3 + 1

    def days_in_month ( self ) -> int:

        return months.monthrange(self.at.year, self.at.month)[1]

    def zone ( self ) -> str:

        return str(self.at.tzinfo)

    def stamp ( self ) -> float:

        return self.at.timestamp()
