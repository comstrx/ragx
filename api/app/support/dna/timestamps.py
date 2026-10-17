from datetime import datetime

from core.date import date


class Timestamps:

    created = "created_at"
    updated = "updated_at"

    def now ( self ) -> datetime:
        return date.now()

    def born ( self, values: dict[str, object] ) -> dict[str, object]:

        moment = self.now()

        return { **values, self.created: moment, self.updated: moment }

    def touch ( self, values: dict[str, object] ) -> dict[str, object]:
        return { **values, self.updated: self.now() }

    def age ( self, moment: datetime ) -> float:
        return date.since(moment)
