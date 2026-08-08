"""Tests for the document loaders (dispatch, PDF, HTML)."""

from unittest.mock import MagicMock, patch

import pytest

from ingestion.loaders.dispatch import UnsupportedFileTypeError, load_document
from ingestion.loaders.html_loader import load_html
from ingestion.loaders.pdf_loader import load_pdf


def test_txt_is_decoded_as_plain_text() -> None:
    assert load_document("notes.txt", b"Hello world.") == "Hello world."


def test_markdown_is_decoded_as_plain_text() -> None:
    text = load_document("README.md", b"# Title\n\nSome body text.")
    assert text == "# Title\n\nSome body text."


def test_extension_matching_is_case_insensitive() -> None:
    assert load_document("NOTES.TXT", b"Hello world.") == "Hello world."


def test_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        load_document("archive.zip", b"whatever")


def test_missing_extension_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        load_document("noextension", b"whatever")


def test_load_html_extracts_visible_text() -> None:
    html = b"<html><body><h1>Title</h1><p>Hello world.</p></body></html>"
    text = load_html(html)
    assert "Title" in text
    assert "Hello world." in text
    assert "<h1>" not in text


def test_dispatch_routes_html_extension_to_html_loader() -> None:
    html = b"<html><body><p>Routed correctly.</p></body></html>"
    assert "Routed correctly." in load_document("page.html", html)


def test_load_pdf_joins_page_text() -> None:
    fake_page_1 = MagicMock()
    fake_page_1.extract_text.return_value = "Page one text."
    fake_page_2 = MagicMock()
    fake_page_2.extract_text.return_value = "Page two text."

    with patch("ingestion.loaders.pdf_loader.PdfReader") as mock_reader_cls:
        mock_reader_cls.return_value.pages = [fake_page_1, fake_page_2]
        result = load_pdf(b"%PDF-fake-bytes")

    assert result == "Page one text.\n\nPage two text."


def test_load_pdf_skips_pages_with_no_extractable_text() -> None:
    empty_page = MagicMock()
    empty_page.extract_text.return_value = ""
    text_page = MagicMock()
    text_page.extract_text.return_value = "Only real content."

    with patch("ingestion.loaders.pdf_loader.PdfReader") as mock_reader_cls:
        mock_reader_cls.return_value.pages = [empty_page, text_page]
        result = load_pdf(b"%PDF-fake-bytes")

    assert result == "Only real content."


def test_dispatch_routes_pdf_extension_to_pdf_loader() -> None:
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "Routed correctly."

    with patch("ingestion.loaders.pdf_loader.PdfReader") as mock_reader_cls:
        mock_reader_cls.return_value.pages = [fake_page]
        assert load_document("doc.pdf", b"%PDF-fake-bytes") == "Routed correctly."
