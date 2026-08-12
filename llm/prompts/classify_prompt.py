"""Prompt for classifying a query into one of three routes."""

from langchain_core.prompts import ChatPromptTemplate

CLASSIFY_PROMPT = ChatPromptTemplate.from_template(
    "Classify the question below into exactly one category:\n\n"
    "RETRIEVE — answering it requires looking up specific information "
    "from the ingested document collection.\n"
    "LOG — it asks about document ingestion/upload history itself, e.g. "
    "what happened during a specific ingestion, when a document was "
    "uploaded, how many chunks it produced, or references an ingestion "
    "by its document ID.\n"
    "DIRECT — it's a greeting, small talk, or a question about what this "
    "assistant can do, answerable without looking anything up.\n\n"
    "Respond with exactly one word: RETRIEVE, LOG, or DIRECT.\n\n"
    "Question: {question}"
)
