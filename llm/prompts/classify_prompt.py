"""Prompt for classifying a query into one of three routes."""

from langchain_core.prompts import ChatPromptTemplate

CLASSIFY_PROMPT = ChatPromptTemplate.from_template(
    "Classify the question below into exactly one category:\n\n"
    "RETRIEVE — answering it accurately requires looking up specific "
    "information from the ingested document collection. This includes "
    "any question asking what a named thing is, how it works, or for "
    "details about it -- even if the name sounds like it could refer to "
    "this assistant or platform itself. Never assume from the name "
    "alone; the document collection is the source of truth, so this is "
    "the default whenever the question names a specific topic.\n"
    "LOG — it asks about document ingestion/upload history itself, e.g. "
    "what happened during a specific ingestion, when a document was "
    "uploaded, how many chunks it produced, or references an ingestion "
    "by its document ID.\n"
    "DIRECT — it's a greeting, small talk, or a generic question about "
    "how to use this API (not about any specific named topic), "
    "answerable without looking anything up.\n\n"
    "Respond with exactly one word: RETRIEVE, LOG, or DIRECT.\n\n"
    "Question: {question}"
)
