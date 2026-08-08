"""Tests for the FAISS VectorStore adapter."""

from pathlib import Path

import pytest

from app.services.faiss_store import FaissVectorStore


def _unit_vectors() -> tuple[list[list[float]], list[str], list[str], list[dict[str, str]]]:
    vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    ids = ["a", "b", "c"]
    texts = ["alpha", "beta", "gamma"]
    metadatas = [{"tag": "a"}, {"tag": "b"}, {"tag": "c"}]
    return vectors, ids, texts, metadatas


def test_add_and_search_round_trip(tmp_path: Path) -> None:
    store = FaissVectorStore(str(tmp_path))
    vectors, ids, texts, metadatas = _unit_vectors()

    store.add(ids=ids, vectors=vectors, texts=texts, metadatas=metadatas)

    assert store.count() == 3

    results = store.search([1.0, 0.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0].id == "a"
    assert results[0].text == "alpha"
    assert results[0].metadata == {"tag": "a"}
    assert results[0].score == pytest.approx(1.0)


def test_search_returns_at_most_top_k_results(tmp_path: Path) -> None:
    store = FaissVectorStore(str(tmp_path))
    vectors, ids, texts, metadatas = _unit_vectors()
    store.add(ids=ids, vectors=vectors, texts=texts, metadatas=metadatas)

    results = store.search([1.0, 0.0, 0.0], top_k=10)

    assert len(results) == 3


def test_search_on_empty_store_returns_no_results(tmp_path: Path) -> None:
    store = FaissVectorStore(str(tmp_path))

    assert store.count() == 0
    assert store.search([1.0, 0.0, 0.0], top_k=5) == []


def test_persists_and_reloads_from_disk(tmp_path: Path) -> None:
    vectors, ids, texts, metadatas = _unit_vectors()

    store = FaissVectorStore(str(tmp_path))
    store.add(ids=ids, vectors=vectors, texts=texts, metadatas=metadatas)

    reloaded = FaissVectorStore(str(tmp_path))

    assert reloaded.count() == 3
    results = reloaded.search([0.0, 1.0, 0.0], top_k=1)
    assert results[0].id == "b"
