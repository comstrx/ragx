from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from core.error import Fault
from core.fs import Bundle, Extraction, ExtractPolicy, Part
import io, tarfile
import pytest

@pytest.mark.anyio
async def test_pdf_text_is_extracted_in_worker_and_pages_bounded ( tmp_path: Path ) -> None:

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 40 220 Td (Refund policy: fourteen days.) Tj ET")
    page[NameObject("/Contents")] = content
    target = tmp_path / "policy.bin"
    with target.open("wb") as stream: writer.write(stream)
    result = await Extraction().extract(target)
    assert result.mime == "application/pdf"
    assert "fourteen days" in result.text
    assert result.parts[0].page == 1
    with pytest.raises(Fault): await Extraction().extract(target, ExtractPolicy(max_chars=4))

def test_bundle_rejects_traversal_and_runtime_tampering ( tmp_path: Path ) -> None:

    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("../escaped")
        member.size = 1
        stream.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(Fault): Bundle().unpack(archive, tmp_path / "runtime")
    assert not (tmp_path / "escaped").exists()

@pytest.mark.anyio
async def test_empty_pdf_requires_explicit_ocr_converter ( tmp_path: Path ) -> None:

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    target = tmp_path / "scanned.pdf"
    with target.open("wb") as stream: writer.write(stream)
    with pytest.raises(Fault) as caught: await Extraction().extract(target)
    assert caught.value.reason == "file.converter.unsupported"

    async def converter ( data: bytes, mime: str, name: str ) -> tuple[Part, ...]:

        assert data.startswith(b"%PDF")
        assert mime == "application/pdf"
        return (Part("fixture OCR result", page=1),)

    extracted = await Extraction().extract(target, converter=converter)
    assert extracted.text == "fixture OCR result"

def test_allowed_root_rejects_symlink_ancestors ( tmp_path: Path ) -> None:

    root = tmp_path / "uploads"
    root.mkdir()
    child = root / "real"
    child.mkdir()
    document = child / "data.txt"
    document.write_text("document")
    (root / "alias").symlink_to(child, target_is_directory=True)
    policy = ExtractPolicy(root=str(root))
    assert Extraction().read(document, policy)[1] == b"document"
    with pytest.raises(Fault): Extraction().read(root / "alias" / "data.txt", policy)
    with pytest.raises(Fault): Extraction().read(root / ".." / "uploads" / "real" / "data.txt", policy)
