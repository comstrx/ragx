from collections.abc import Awaitable, Callable

from engine.fs import Extraction
from engine.test import Bench, Measured, Work, sample
import asyncio

ARABIC  = "يمكن طلب الاسترداد خلال أربعة عشر يوما من الاستلام. The invoice INV-2026-0042 is paid."
PAGES   = tuple(f"Policy page {index}: refunds within {index + 10} days of delivery." for index in range(20))
ROWS    = [["city", "clients", "revenue"], *([f"city-{row}", str(row), str(row * 13)] for row in range(2000))]
ROUNDS  = 20

class ExtractBench(Bench):

    def run ( self ) -> None:

        self.quiet()
        asyncio.run(self.extract())

    def timed ( self, work: Work ) -> Callable[[], Awaitable[Measured]]:

        return lambda: self.measure(work, ROUNDS, 1)

    async def extract ( self ) -> None:

        files  = Extraction()
        pdf    = sample.pdf(*PAGES)
        word   = sample.docx(*([ARABIC] * 200))
        sheet  = sample.xlsx("sales", ROWS)
        sound  = sample.wav(30.0, "call")
        plain  = (ARABIC * 400).encode()

        async def text () -> None:

            await files.parse("notes.txt", plain)

        async def pages () -> None:

            await files.parse("policy.pdf", pdf)

        async def document () -> None:

            await files.parse("policy.docx", word)

        async def table () -> None:

            await files.parse("sales.xlsx", sheet)

        async def media () -> None:

            await files.parse("call.wav", sound)

        async def clip () -> None:

            await files.clip(sound, 5.0, 15.0)

        async def render () -> None:

            await files.render(pdf, 1)

        for label, work, budget in (
            ("extract.text",    text,     5.0),
            ("extract.pdf20",   pages,    600.0),
            ("extract.docx",    document, 600.0),
            ("extract.xlsx2k",  table,    600.0),
            ("extract.wav",     media,    600.0),
            ("extract.clip10s", clip,     600.0),
            ("extract.render",  render,   600.0),
        ):

            await self.asettle(label, self.timed(work), budget)

if __name__ == "__main__":

    ExtractBench().run()
