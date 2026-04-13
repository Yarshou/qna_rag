import re
from collections import Counter

from app.knowledge.models import KnowledgeDocument

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
WHITESPACE_PATTERN = re.compile(r"\s+")
SNIPPET_LENGTH = 180


def normalize_whitespace(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def tokenize(value: str) -> list[str]:
    return TOKEN_PATTERN.findall(value.lower())


def score_document(document: KnowledgeDocument, query: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    unique_query_tokens = list(dict.fromkeys(query_tokens))
    filename_tokens = tokenize(document.filename)
    content_tokens = tokenize(document.content)
    token_counts = Counter(content_tokens)

    matched_tokens = [token for token in unique_query_tokens if token_counts[token] > 0 or token in filename_tokens]
    if not matched_tokens:
        return 0.0

    coverage_score = (len(matched_tokens) / len(unique_query_tokens)) * 10.0
    frequency_score = float(sum(min(token_counts[token], 5) for token in unique_query_tokens))
    filename_score = float(sum(1 for token in unique_query_tokens if token in filename_tokens) * 3)

    normalized_query = normalize_whitespace(" ".join(unique_query_tokens))
    normalized_content = normalize_whitespace(document.content.lower())
    phrase_score = 4.0 if normalized_query and normalized_query in normalized_content else 0.0

    return coverage_score + frequency_score + filename_score + phrase_score


def build_snippet(document: KnowledgeDocument, query: str) -> str:
    normalized_content = normalize_whitespace(document.content)
    if not normalized_content:
        return ""

    query_tokens = tokenize(query)
    lowered_content = normalized_content.lower()

    for token in query_tokens:
        match_index = lowered_content.find(token)
        if match_index < 0:
            continue

        start = max(0, match_index - 60)
        end = min(len(normalized_content), match_index + len(token) + 100)
        snippet = normalized_content[start:end].strip()
        if start > 0:
            snippet = f"...{snippet}"
        if end < len(normalized_content):
            snippet = f"{snippet}..."
        return snippet

    excerpt = normalized_content[:SNIPPET_LENGTH].strip()
    if len(normalized_content) > SNIPPET_LENGTH:
        return f"{excerpt}..."
    return excerpt
