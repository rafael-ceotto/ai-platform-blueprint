"""Prompt template for RAG answer generation."""

from langchain_core.prompts import ChatPromptTemplate

RAG_PROMPT = ChatPromptTemplate.from_template(
    "You are an assistant answering questions using only the provided "
    "context. If the answer isn't contained in the context, say you "
    "don't have enough information — do not guess. Always answer in the "
    "same language the question was asked in.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)
