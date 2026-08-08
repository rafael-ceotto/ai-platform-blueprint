"""Splits raw text into overlapping chunks sized for embedding.

Paragraph-aware: whole paragraphs (blank-line separated) are packed
together as long as they fit within `chunk_size`. A paragraph that alone
exceeds `chunk_size` falls back to a word-boundary sliding window so no
chunk exceeds the configured size.
"""


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split `text` into chunks of at most `chunk_size` characters each.

    Consecutive chunks produced by the sliding-window fallback overlap by
    up to `chunk_overlap` characters, preserving context across the split.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= chunk_size:
            current = paragraph
        else:
            chunks.extend(_split_long_paragraph(paragraph, chunk_size, chunk_overlap))

    if current:
        chunks.append(current)

    return chunks


def _split_long_paragraph(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Sliding-word-window split for a single paragraph longer than `chunk_size`."""
    words = text.split()
    chunks: list[str] = []
    window: list[str] = []
    window_len = 0

    i = 0
    while i < len(words):
        word = words[i]
        added_len = len(word) + (1 if window else 0)

        if window and window_len + added_len > chunk_size:
            chunks.append(" ".join(window))
            window, window_len = _trailing_overlap(window, chunk_overlap)
            continue

        window.append(word)
        window_len += added_len
        i += 1

    if window:
        chunks.append(" ".join(window))

    return chunks


def _trailing_overlap(window: list[str], chunk_overlap: int) -> tuple[list[str], int]:
    """Return the trailing words of `window` that fit within `chunk_overlap` chars."""
    overlap_words: list[str] = []
    overlap_len = 0

    for word in reversed(window):
        word_len = len(word) + (1 if overlap_words else 0)
        if overlap_len + word_len > chunk_overlap:
            break
        overlap_words.insert(0, word)
        overlap_len += word_len

    return overlap_words, overlap_len
