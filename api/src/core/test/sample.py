from collections.abc import Sequence
import io, math, struct, zipfile, zlib

OPC   = "http://schemas.openxmlformats.org/package/2006"
REL   = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CELLS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
MAIN  = "application/vnd.openxmlformats-officedocument"
RATE  = 16_000
PITCH = 440
LOUD  = 8000
RELS  = (
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
)
INK   = b"q 100 0 0 100 50 50 cm BI /W 2 /H 2 /CS /G /BPC 8 ID \x00\xff\xff\x00 EI Q"

class Samples:

    def pdf ( self, *pages: str ) -> bytes:

        font    = "<< /Font << /F1 3 0 R >> >>"
        streams = [f"BT /F1 12 Tf 40 220 Td ({text}) Tj ET".encode() if text else b"" for text in pages]

        return self.document(streams, f"/Resources {font}")

    def scanned ( self, pages: int = 1 ) -> bytes:

        return self.document([INK] * pages)

    def document ( self, streams: Sequence[bytes], resources: str = "" ) -> bytes:

        count   = len(streams)
        kids    = " ".join(f"{4 + index * 2} 0 R" for index in range(count))
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]

        for index, stream in enumerate(streams):

            page = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] {resources} /Contents {5 + index * 2} 0 R >>"

            objects.extend((page.encode(), b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)))

        body    = b"%PDF-1.4\n"
        offsets = []

        for number, item in enumerate(objects, 1):

            offsets.append(len(body))

            body += b"%d 0 obj\n%s\nendobj\n" % (number, item)

        table = b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
        size  = len(objects) + 1

        return body + b"xref\n0 %d\n0000000000 65535 f \n%s" % (size, table) + (
            b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, len(body))
        )

    def zipped ( self, parts: dict[str, str] ) -> bytes:

        stream = io.BytesIO()

        with zipfile.ZipFile(stream, "w") as archive:

            for name, text in parts.items(): archive.writestr(name, text)

        return stream.getvalue()

    def package ( self, kind: str, part: str, body: str, extra: dict[str, str] | None = None ) -> bytes:

        return self.zipped({
            "[Content_Types].xml": f'<Types xmlns="{OPC}/content-types">{RELS}<Override PartName="/{part}" '
                f'ContentType="{MAIN}.{kind}"/></Types>',
            "_rels/.rels": f'<Relationships xmlns="{OPC}/relationships"><Relationship Id="r1" '
                f'Type="{REL}/officeDocument" Target="{part}"/></Relationships>',
            part: body, **(extra or {}),
        })

    def docx ( self, *paragraphs: str ) -> bytes:

        runs = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
        body = f'<w:document xmlns:w="{WORD}"><w:body>{runs}</w:body></w:document>'

        return self.package("wordprocessingml.document.main+xml", "word/document.xml", body)

    def xlsx ( self, name: str, rows: Sequence[Sequence[str]] ) -> bytes:

        cells = "".join(
            f'<row r="{line}">' + "".join(
                f'<c r="{chr(65 + column)}{line}" t="inlineStr"><is><t>{value}</t></is></c>'
                for column, value in enumerate(row)
            ) + "</row>" for line, row in enumerate(rows, 1)
        )
        book  = f'<workbook xmlns="{CELLS}" xmlns:r="{REL}"><sheets><sheet name="{name}" sheetId="1" r:id="r1"/>'
        links = f'<Relationships xmlns="{OPC}/relationships"><Relationship Id="r1" Type="{REL}/worksheet" '

        return self.package("spreadsheetml.sheet.main+xml", "xl/workbook.xml", f"{book}</sheets></workbook>", {
            "xl/_rels/workbook.xml.rels": f'{links}Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{CELLS}"><sheetData>{cells}</sheetData></worksheet>',
        })

    def wav ( self, seconds: float, title: str = "" ) -> bytes:

        levels = (int(LOUD * math.sin(2 * math.pi * PITCH * at / RATE)) for at in range(int(RATE * seconds)))
        tone   = b"".join(struct.pack("<h", level) for level in levels)
        name   = title.encode() + b"\x00"
        name  += b"\x00" * (len(name) % 2)
        info   = b"INFO" + b"INAM" + struct.pack("<I", len(name)) + name if title else b""
        listed = b"LIST" + struct.pack("<I", len(info)) + info if info else b""
        shape  = struct.pack("<HHIIHH", 1, 1, RATE, RATE * 2, 2, 16)
        body   = b"WAVE" + b"fmt " + struct.pack("<I", 16) + shape + listed
        body  += b"data" + struct.pack("<I", len(tone)) + tone

        return b"RIFF" + struct.pack("<I", len(body)) + body

    def png ( self, red: int, green: int, blue: int, side: int = 64 ) -> bytes:

        def chunk ( kind: bytes, data: bytes ) -> bytes:

            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        rows = b"".join(b"\x00" + bytes((red, green, blue)) * side for _ in range(side))
        head = struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0)

        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
