from collections.abc import Mapping

from fastapi import FastAPI, Request

type Known = Mapping[str, object]

class Facts:

    @staticmethod
    def keep ( app: FastAPI, facts: Known ) -> None:

        app.state.facts = dict(facts)

    @staticmethod
    def of ( request: Request ) -> Known:

        facts: object = getattr(request.app.state, "facts", {})

        return facts if isinstance(facts, Mapping) else {}
