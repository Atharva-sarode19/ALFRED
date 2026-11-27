import io
import unittest
import zipfile

from app.services.documents import (
    DocumentError,
    chunk_text,
    detect_kind,
    extract_text,
    sanitize_filename,
)

LIMIT = 1024 * 1024


def make_docx(paragraphs, *, extra_xml=b""):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = (
        extra_xml
        + b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + body.encode()
        + b"</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


class ValidationTests(unittest.TestCase):
    def test_rejects_unknown_extension(self):
        with self.assertRaises(DocumentError):
            detect_kind("virus.exe", b"MZ...", LIMIT)

    def test_rejects_fake_pdf(self):
        with self.assertRaises(DocumentError):
            detect_kind("a.pdf", b"not a pdf", LIMIT)

    def test_rejects_fake_docx(self):
        with self.assertRaises(DocumentError):
            detect_kind("a.docx", b"plain text pretending", LIMIT)

    def test_rejects_binary_txt_empty_and_oversize(self):
        with self.assertRaises(DocumentError):
            detect_kind("a.txt", b"abc\x00def", LIMIT)
        with self.assertRaises(DocumentError):
            detect_kind("a.txt", b"", LIMIT)
        with self.assertRaises(DocumentError):
            detect_kind("a.txt", b"x" * 20, 10)

    def test_accepts_valid_files(self):
        self.assertEqual(detect_kind("a.txt", b"hello", LIMIT), "txt")
        self.assertEqual(detect_kind("A.PDF", b"%PDF-1.7 ...", LIMIT), "pdf")
        self.assertEqual(detect_kind("a.docx", make_docx(["hi"]), LIMIT), "docx")

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("../../etc/passwd"), "passwd")
        self.assertEqual(sanitize_filename("C:\\Users\\me\\report.docx"), "report.docx")
        self.assertEqual(sanitize_filename("a\x00b\n.txt"), "ab.txt")
        self.assertEqual(sanitize_filename(""), "document")


class ExtractionTests(unittest.TestCase):
    def test_txt_utf8_and_cp1252(self):
        self.assertEqual(extract_text("txt", "caf\u00e9".encode("utf-8")), "caf\u00e9")
        self.assertEqual(extract_text("txt", "caf\u00e9".encode("cp1252")), "caf\u00e9")

    def test_docx_paragraphs(self):
        self.assertEqual(extract_text("docx", make_docx(["First", "Second"])), "First\nSecond")

    def test_docx_with_doctype_is_rejected(self):
        data = make_docx(["x"], extra_xml=b'<!DOCTYPE foo [<!ENTITY a "b">]>')
        with self.assertRaises(DocumentError):
            extract_text("docx", data)

    def test_empty_text_is_an_error(self):
        with self.assertRaises(DocumentError):
            extract_text("txt", b"   \n  ")


class ChunkingTests(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(chunk_text("short"), ["short"])

    def test_long_text_is_covered_with_overlap(self):
        text = " ".join(f"Sentence number {i}." for i in range(400))
        chunks = chunk_text(text, size=500, overlap=80)
        self.assertGreater(len(chunks), 5)
        self.assertTrue(all(len(c) <= 500 for c in chunks))
        self.assertIn("Sentence number 0.", chunks[0])
        self.assertIn("Sentence number 399.", chunks[-1])


if __name__ == "__main__":
    unittest.main()
