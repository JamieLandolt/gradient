"""Turn an uploaded ECP file into plain text for the extraction pipeline.

Course profiles are usually distributed as PDFs; students may also paste a
saved `.txt`. Extraction only ever sees this public course text — never student
data (FR-3.5.5). PDF parsing is local and fast, so it runs in the request (off
the event loop, in a worker thread); the slow LLM extraction is what moves to a
background task.

The parse is bounded (page count + a running character budget) so a small
"decompression-bomb" PDF whose streams expand enormously cannot exhaust memory
or pin a core before the size check runs.
"""

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError

# Bounds on how much work a single hostile/large file can cause. ECPs are a
# handful of pages; anything past these caps is rejected or truncated.
MAX_PDF_PAGES = 200
MAX_TEXT_CHARS = 100_000


def extract_pdf_text(data: bytes) -> str:
    """Extract page text from a PDF byte string, bounded by page count and a
    running character budget.

    Raises ``ValueError`` if the bytes are not a readable PDF (or blow the page
    cap) so the caller can surface a clean 422 rather than a 500.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages
        if len(pages) > MAX_PDF_PAGES:
            raise ValueError(f"too many pages ({len(pages)} > {MAX_PDF_PAGES})")
        parts: list[str] = []
        total = 0
        for page in pages:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total > MAX_TEXT_CHARS:
                # Stop before materialising an unbounded amount of text; the
                # endpoint's own char cap then rejects the over-long result.
                break
        return "\n".join(parts).strip()
    except (PyPdfError, OSError, ValueError) as exc:
        raise ValueError(f"the file is not a readable PDF ({exc})") from exc


def extract_upload_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Decode an uploaded file to text, choosing PDF parsing vs UTF-8 by type.

    Raises ``ValueError`` on an unreadable PDF or non-UTF-8 text file. Runs
    synchronously (CPU-bound); callers on the event loop should offload it to a
    worker thread.
    """
    name = filename.lower()
    if name.endswith(".pdf") or content_type == "application/pdf":
        return extract_pdf_text(data)
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("the file is not valid UTF-8 text") from exc
