from .strand import Kit, Strand

class String(Kit):

    def of ( self, value: object ) -> Strand:

        if value is None: return Strand()
        if isinstance(value, bytes | bytearray): return Strand(bytes(value).decode(errors="replace"))

        return Strand(value)

    def is_empty ( self, value: object ) -> bool:

        return self.of(value).strip() == ""

    def limit ( self, text: str, limit: int, suffix: str = "…" ) -> str:

        return self.truncate(text, limit, suffix)

    def length ( self, text: str ) -> int:

        return len(text)
