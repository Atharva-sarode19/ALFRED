"""
Document validation, text extraction and chunking for uploaded files.

Supported formats: PDF, DOCX, TXT. Validation checks the extension, size and
the file's real content signature (not just its name). DOCX is read with the
stdlib (zip + XML) and PDF with `pypdf` (pure Python, imported lazily).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}
MAX_EXTRACTED_CHARS = 2_000_000
MAX_DOCX_XML_BYTES = 50 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(ValueError):
    """The file is unsupported, invalid, or has no readable text."""


def sanitize_filename(name: str) -> str:
    """Display-safe file name: no path parts, no control characters, bounded length."""
    base = re.split(r"[\\/]", name or "")[-1]
    cleaned = "".join(ch for ch in base if ch.isprintable()).strip().strip(".")
    return (cleaned or "document")[:120]


def detect_kind(filename: str, data: bytes, max_bytes: int) -> str:
    """Validate an upload and return its kind ('pdf' | 'docx' | 'txt')."""
    if not data:
        raise DocumentError("The file is empty.")
    if len(data) > max_bytes:
        raise DocumentError(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.")

    lowered = sanitize_filename(filename).lower()
    kind = next((k for ext, k in ALLOWED_EXTENSIONS.items() if lowered.endswith(ext)), None)
    if kind is None:
        raise DocumentError("Unsupported file type. Upload a PDF, DOCX or TXT file.")

    if kind == "pdf" and not data.lstrip()[:5] == b"%PDF-":
        raise DocumentError("This file is not a valid PDF.")
    if kind == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "word/document.xml" not in zf.namelist():
                    raise DocumentError("This file is not a valid DOCX document.")
        except zipfile.BadZipFile as exc:
            raise DocumentError("This file is not a valid DOCX document.") from exc
    if kind == "txt" and b"\x00" in data[:8192]:
        raise DocumentError("This file does not look like plain text.")
    return kind


def extract_text(kind: str, data: bytes) -> str:
    if kind == "pdf":
        text = _extract_pdf(data)
    elif kind == "docx":
        text = _extract_docx(data)
    elif kind == "txt":
        text = _decode_text(data)
    else:
        raise DocumentError("Unsupported file type.")

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise DocumentError(
            "No readable text was found. Scanned or image-only documents are not supported yet."
        )
    return text[:MAX_EXTRACTED_CHARS]


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            info = zf.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise DocumentError("This document is too large to read.")
            xml_bytes = zf.read(info)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise DocumentError("This file is not a valid DOCX document.") from exc

    # ElementTree does not expand external entities, but reject DTDs outright
    # so a crafted file cannot attempt entity-expansion tricks.
    if b"<!DOCTYPE" in xml_bytes or b"<!ENTITY" in xml_bytes:
        raise DocumentError("This DOCX contains unsupported XML.")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DocumentError("This DOCX could not be parsed.") from exc

    paragraphs: list[str] = []
    for para in root.iter(f"{_W}p"):
        parts: list[str] = []
        for el in para.iter():
            if el.tag == f"{_W}t":
                parts.append(el.text or "")
            elif el.tag == f"{_W}tab":
                parts.append("\t")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise DocumentError("PDF support needs `pip install pypdf`.") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError("This PDF is password protected.")
        pages: list[str] = []
        total = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            pages.append(page_text)
            total += len(page_text)
            if total >= MAX_EXTRACTED_CHARS:
                break
        return "\n\n".join(pages)
    except DocumentError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf raises many exception types
        raise DocumentError("This PDF could not be read.") from exc


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence boundaries."""
    chunks: list[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            window_start = start + int(size * 0.6)
            cut = max(
                text.rfind("\n\n", window_start, end),
                text.rfind(". ", window_start, end),
                text.rfind("\n", window_start, end),
            )
            if cut != -1:
                end = cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = end - overlap if end - overlap > start else end
    return chunks
