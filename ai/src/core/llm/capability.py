from dataclasses import dataclass
from core.error import Code, Fault

@dataclass(frozen=True, slots=True)
class Capabilities:

    generate          : bool = True
    stream            : bool = True
    embed             : bool = False
    rank              : bool = False
    json              : bool = False
    schema            : bool = False
    image             : bool = False
    audio             : bool = False
    video             : bool = False
    pdf               : bool = False
    embedding_instruction : bool = False

    def require ( self, operation: str ) -> None:

        if not getattr(self, operation, False):
            raise Fault(Code.VALIDATION, reason=f"llm.unsupported.{operation}")
