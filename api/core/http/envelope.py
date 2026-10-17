from collections.abc import Mapping

from core.context import context
from core.error import Code, Fault

type Payload = dict[str, object]


class Envelope:

    @staticmethod
    def success (
        data: object = None, message: str | None = None,
        code: Code = Code.OK, meta: Mapping[str, object] | None = None,
    ) -> Payload:

        return Envelope.build(data, message, None, code, None, meta)

    @staticmethod
    def failure ( fault: Fault, meta: Mapping[str, object] | None = None ) -> Payload:
        return Envelope.build(None, fault.message, fault.errors, fault.code, fault.reason, meta)

    @staticmethod
    def build (
        data: object, message: str | None, errors: Mapping[str, list[str]] | None,
        code: Code, reason: str | None, meta: Mapping[str, object] | None,
    ) -> Payload:

        return {
            "data"    : data,
            "message" : message,
            "errors"  : dict(errors) if errors else None,
            "code"    : code,
            "reason"  : reason,
            "meta"    : { "request_id": context.request_id(), **(meta or {}) },
        }
