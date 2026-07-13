"""Uploaded-file text extraction (PDF + plain text)."""

import io

import pytest

from app.ingestion.pdf import extract_pdf_text, extract_upload_text


def make_pdf(text: str) -> bytes:
    """Build a minimal single-page PDF with one line of extractable text.

    Offsets in the xref table are computed so pypdf parses it via the xref —
    lets the tests round-trip a real PDF without a committed binary fixture.
    """
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,  # content stream, filled below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 24 Tf 72 700 Td (" + text.encode("latin-1") + b") Tj ET"
    objs[3] = (
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream"
    )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(b"xref\n0 " + str(len(objs) + 1).encode() + b"\n")
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\n")
    out.write(b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF")
    return out.getvalue()


def test_extract_pdf_text_reads_page_text():
    data = make_pdf("Course code: TEST1000")

    assert "Course code: TEST1000" in extract_pdf_text(data)


def test_extract_pdf_text_rejects_non_pdf_bytes():
    with pytest.raises(ValueError):
        extract_pdf_text(b"this is definitely not a pdf")


def test_extract_upload_text_routes_pdf_by_extension():
    data = make_pdf("Course code: TEST2000")

    assert "TEST2000" in extract_upload_text(data, filename="profile.pdf")


def test_extract_upload_text_routes_pdf_by_content_type():
    data = make_pdf("Course code: TEST3000")

    assert "TEST3000" in extract_upload_text(data, content_type="application/pdf")


def test_extract_upload_text_decodes_plain_text():
    assert extract_upload_text(b"Course code: TEST4000\n", filename="ecp.txt") == (
        "Course code: TEST4000"
    )


def test_extract_upload_text_rejects_non_utf8_text():
    with pytest.raises(ValueError):
        extract_upload_text(b"\xff\xfe not utf-8", filename="ecp.txt")
