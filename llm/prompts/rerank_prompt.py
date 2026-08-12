"""Prompt + parsing for LLM-based re-ranking of retrieved candidates."""

import re

from langchain_core.prompts import ChatPromptTemplate

RERANK_PROMPT = ChatPromptTemplate.from_template(
    "Given the question and the numbered candidate passages below, list "
    "the passage numbers in order of relevance to the question, most "
    "relevant first. Respond with only a comma-separated list of "
    'numbers (e.g. "3,1,2"), nothing else.\n\n'
    "Question: {question}\n\n"
    "Candidates:\n{candidates}"
)


def parse_ranking(response: str, count: int) -> list[int]:
    """Parse a comma-separated ranking like "3,1,2" into a 0-indexed order.

    Falls back to the original order (`range(count)`) if the response
    isn't a valid permutation of the candidate indices -- a malformed
    rerank response from the model should never fail the request.
    """
    order = [int(n) - 1 for n in re.findall(r"\d+", response)]
    if sorted(order) == list(range(count)):
        return order
    return list(range(count))
