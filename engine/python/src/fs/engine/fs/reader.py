from collections.abc import Callable
from typing import Any, NoReturn
import io, json, re, sys, unicodedata

lazy import kreuzberg
lazy import pypdfium2 as pdfium
lazy import pypdfium2.raw as native
lazy from charset_normalizer import from_bytes
lazy from pypdf import PdfReader
lazy from pypdf.errors import PyPdfError
lazy from python_calamine import CalamineError, CalamineWorkbook

ARABIC     = re.compile(r"[\u0600-\u06FF]{2,}")
FORMS      = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]+")
NOISE      = re.compile(r"[\uFFFD\uE000-\uF8FF\x00-\x08\x0B\x0C\x0E-\x1F]")
MIXED      = re.compile(r"[\u0600-\u06FF][\u0100-\u02AF]|[\u0100-\u02AF][\u0600-\u06FF]")
PICTURE    = re.compile(r"!\[[^\]]*\]\([^)]*\)")
FINALS     = "\u0629\u0649"
LEAST      = 16
FLIPPED    = 50
NOISY      = 50
PIXELS     = 40_000_000
SHEETS     = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12", "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.oasis.opendocument.spreadsheet",
})
CONTAINERS = frozenset({"application/zip", "application/x-ole-storage"})
ARCHIVES   = ("application/x-", "application/gzip", "application/zstd")
RAW        = frozenset({
    "text/plain", "text/markdown", "text/csv", "text/tab-separated-values", "application/json", "application/x-yaml",
})

def write ( data: bytes ) -> None:

    sys.stdout.buffer.write(data)

def emit ( found: object ) -> None:

    write(json.dumps(found, ensure_ascii=False).encode())

def refuse ( reason: str ) -> NoReturn:

    emit({ "error": reason })

    sys.exit(1)

def folded ( text: str ) -> str:

    return FORMS.sub(lambda match: unicodedata.normalize("NFKC", match.group()), text)

def legible ( text: str ) -> bool:

    words   = ARABIC.findall(text)
    flipped = sum(1 for word in words if word[0] in FINALS)
    noise   = len(NOISE.findall(text)) + len(MIXED.findall(text))

    return flipped * FLIPPED <= len(words) and noise * NOISY <= max(len(text), 1)

def bounded ( parts: list[dict[str, Any]], limits: dict[str, Any] ) -> list[dict[str, Any]]:

    if sum(len(part["text"]) for part in parts) > limits["chars"]: refuse("text")

    return parts

def pdf ( data: bytes, limits: dict[str, Any] ) -> dict[str, Any]:

    try: document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError: refuse("pdf")

    if len(document) > limits["pages"]: refuse("pages")

    texts: dict[int, str | None] = {}
    drawn: set[int] = set()

    for index in range(len(document)):

        page         = document[index]
        texts[index] = folded(page.get_textpage().get_text_bounded())

        if any(True for _ in page.get_objects(filter=(native.FPDF_PAGEOBJ_IMAGE,))): drawn.add(index)

    broken = [index for index, text in texts.items() if text and len(text.strip()) >= LEAST and not legible(text)]

    if broken: texts.update(repaired(data, broken))

    parts = [
        { "text": text, "page": index + 1 } for index, text in texts.items()
        if text and len(text.strip()) >= LEAST
    ]
    gaps  = [
        { "kind": "ocr", "page": index + 1 } for index, text in texts.items()
        if text is None or (len((text or "").strip()) < LEAST and index in drawn)
    ]

    return { "mime": "application/pdf", "parts": bounded(parts, limits), "gaps": gaps }

def repaired ( data: bytes, broken: list[int] ) -> dict[int, str | None]:

    try: pages = PdfReader(io.BytesIO(data), strict=False).pages
    except PyPdfError: return dict.fromkeys(broken)

    found: dict[int, str | None] = {}

    for index in broken:

        try: text = folded(pages[index].extract_text())
        except PyPdfError: text = ""

        found[index] = text if legible(text) else None

    return found

def sheet ( data: bytes, mime: str, limits: dict[str, Any] ) -> dict[str, Any]:

    try: book = CalamineWorkbook.from_filelike(io.BytesIO(data))
    except CalamineError: refuse("sheet")

    parts: list[dict[str, Any]] = []
    total = 0

    for number, name in enumerate(book.sheet_names, 1):

        rows  = book.get_sheet_by_name(name).to_python(skip_empty_area=True)
        lines = ["\t".join(str(cell) for cell in row) for row in rows]
        text  = "\n".join([f"## {name}", *lines])
        total += len(text)

        if total > limits["chars"]: refuse("text")
        if lines: parts.append({ "text": text, "page": number })

    return { "mime": mime, "parts": parts, "gaps": [] }

def document ( data: bytes, mime: str, limits: dict[str, Any] ) -> dict[str, Any]:

    config = kreuzberg.ExtractionConfig(use_cache=False, output_format="markdown")

    try: found = kreuzberg.extract_bytes_sync(data, mime, config)
    except kreuzberg.KreuzbergError: refuse("document")
    except RuntimeError: refuse("unsupported")

    written = folded(PICTURE.sub("", found.content))
    parts   = [{ "text": written }] if written.strip() else []

    return { "mime": found.mime_type or mime, "parts": bounded(parts, limits), "gaps": [] }

def decoded ( data: bytes ) -> str:

    try: return data.decode("utf-8-sig")
    except UnicodeDecodeError: pass

    best = from_bytes(data).best()

    if best is None: refuse("encoding")

    return str(best)

def text ( data: bytes, mime: str, limits: dict[str, Any] ) -> dict[str, Any]:

    written = decoded(data)
    parts   = [{ "text": written }] if written.strip() else []

    if mime not in RAW: return document(written.encode(), mime, limits)

    return { "mime": mime, "parts": bounded(parts, limits), "gaps": [] }

def refined ( data: bytes, mime: str ) -> str:

    if mime not in CONTAINERS: return mime

    try: found = kreuzberg.detect_mime_type(data)
    except RuntimeError: refuse("unsupported")

    if found in CONTAINERS or found.startswith(ARCHIVES): refuse("archive")

    return found

def read ( data: bytes, given: str, limits: dict[str, Any] ) -> dict[str, Any]:

    mime = refined(data, given)

    if mime == "application/pdf": return pdf(data, limits)
    if mime in SHEETS: return sheet(data, mime, limits)
    if mime.startswith("text/") or mime in RAW: return text(data, mime, limits)

    return document(data, mime, limits)

def render ( data: bytes, page: int, scale: float ) -> bytes:

    try: document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError: refuse("pdf")

    if not 1 <= page <= len(document): refuse("page")

    width, height = document[page - 1].get_size()

    if width * height * scale * scale > PIXELS: refuse("pixels")

    image  = document[page - 1].render(scale=scale).to_pil()
    stream = io.BytesIO()

    image.save(stream, "PNG", optimize=False)

    return stream.getvalue()

ACTIONS: dict[str, Callable[[bytes, dict[str, Any]], None]] = {
    "read"   : lambda data, limits: emit(read(data, limits["mime"], limits)),
    "render" : lambda data, limits: write(render(data, int(limits["page"]), float(limits["scale"]))),
}

def main () -> None:

    action, limits = sys.argv[1], json.loads(sys.argv[2])

    if action not in ACTIONS: refuse("action")

    ACTIONS[action](sys.stdin.buffer.read(), limits)

if __name__ == "__main__":

    main()
