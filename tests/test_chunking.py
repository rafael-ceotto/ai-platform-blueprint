"""Tests for the chunking service."""

import pytest

from ingestion.chunking.chunker import chunk_text


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("", chunk_size=100, chunk_overlap=10) == []
    assert chunk_text("   \n\n  ", chunk_size=100, chunk_overlap=10) == []


def test_short_text_returns_single_chunk() -> None:
    chunks = chunk_text("Hello world.", chunk_size=100, chunk_overlap=10)
    assert chunks == ["Hello world."]


def test_paragraphs_pack_together_when_they_fit() -> None:
    text = "First paragraph.\n\nSecond paragraph."
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=10)
    assert chunks == ["First paragraph.\n\nSecond paragraph."]


def test_paragraphs_split_when_they_do_not_fit() -> None:
    para_a = "a" * 40
    para_b = "b" * 40
    text = f"{para_a}\n\n{para_b}"
    chunks = chunk_text(text, chunk_size=50, chunk_overlap=5)
    assert chunks == [para_a, para_b]


def test_long_paragraph_is_split_with_overlap() -> None:
    words = [f"word{i}" for i in range(50)]
    text = " ".join(words)

    chunks = chunk_text(text, chunk_size=40, chunk_overlap=10)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 40

    # consecutive chunks should share trailing/leading words (the overlap)
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    assert any(w in second_words[: len(first_words)] for w in first_words[-1:])

    # every original word must still appear somewhere in the output
    reconstructed = " ".join(chunks).split()
    assert set(words).issubset(set(reconstructed))


def test_invalid_chunk_size_raises() -> None:
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=0, chunk_overlap=0)


def test_overlap_not_smaller_than_chunk_size_raises() -> None:
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=10, chunk_overlap=10)
