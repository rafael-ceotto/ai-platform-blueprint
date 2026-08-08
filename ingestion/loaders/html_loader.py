"""Extracts readable text from an HTML file."""

from bs4 import BeautifulSoup


def load_html(content: bytes) -> str:
    soup = BeautifulSoup(content, "html.parser")
    return soup.get_text(separator="\n\n", strip=True)
