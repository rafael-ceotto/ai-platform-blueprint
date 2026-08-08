"""Dispatches a file to the right loader by extension.

`.txt`/`.md`/`.markdown` need no extraction library — markdown is
already plain text and chunks/embeds fine as-is. Only `.pdf` and
`.html`/`.htm` need real parsing. See docs/adr/0005-document-loaders.md.
"""

from ingestion.loaders.html_loader import load_html
from ingestion.loaders.pdf_loader import load_pdf

_PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
_HTML_EXTENSIONS = {".html", ".htm"}


class UnsupportedFileTypeError(Exception):
    pass


def load_document(filename: str, content: bytes) -> str:
    """Extract text from `content` based on `filename`'s extension."""
    suffix = _extension(filename)

    if suffix in _PLAIN_TEXT_EXTENSIONS:
        return content.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        return load_pdf(content)
    if suffix in _HTML_EXTENSIONS:
        return load_html(content)

    raise UnsupportedFileTypeError(f"Unsupported file type: {suffix or '(no extension)'}")


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""
