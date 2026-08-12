"""Prompt for answering a query directly, without retrieval."""

from langchain_core.prompts import ChatPromptTemplate

DIRECT_ANSWER_PROMPT = ChatPromptTemplate.from_template(
    "You are the assistant for an AI platform's document search API. "
    "Answer the question briefly and helpfully; you have no document "
    "context for this one. Always answer in the same language the "
    "question was asked in.\n\n"
    "Question: {question}"
)
