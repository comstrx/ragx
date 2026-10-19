from pypdf import PdfReader
import io, json, resource, sys

MEMORY = 768 * 1024 * 1024

def main () -> None:

    resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()), strict=True)
    pages, chars = int(sys.argv[1]), int(sys.argv[2])

    if reader.is_encrypted or len(reader.pages) > pages: sys.exit(2)

    result: list[dict[str, str | int]] = []
    total = 0

    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text(extraction_mode="layout")
        total += len(text)
        if total > chars: sys.exit(3)
        result.append({"page": number, "text": text})

    sys.stdout.write(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":

    main()
