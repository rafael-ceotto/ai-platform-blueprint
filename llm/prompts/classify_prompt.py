"""Prompt for classifying whether a query needs retrieval."""

from langchain_core.prompts import ChatPromptTemplate

CLASSIFY_PROMPT = ChatPromptTemplate.from_template(
    "Decide whether answering the question below requires looking up "
    "specific information from a document collection, or whether it's a "
    "greeting, small talk, or a question about what this assistant can "
    "do that you can answer directly.\n\n"
    "Respond with exactly one word: RETRIEVE or DIRECT.\n\n"
    "Question: {question}"
)
