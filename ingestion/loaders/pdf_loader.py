"""Extracts text from a PDF file."""

import io

from pypdf import PdfReader


def load_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = (page.extract_text() or "" for page in reader.pages)
    return "\n\n".join(text for text in pages if text)
