from engine.date import DateTime, date

class Timestamps:

    created = "created_at"
    updated = "updated_at"

    def now ( self ) -> DateTime:

        return date.now()

    def born ( self, values: dict[str, object] ) -> dict[str, object]:

        moment = self.now()

        return { **values, self.created: moment, self.updated: moment }

    def touch ( self, values: dict[str, object] ) -> dict[str, object]:

        return { **values, self.updated: self.now() }

    def age ( self, moment: DateTime ) -> float:

        return date.since(moment)
