import os
from typing import Any, Optional

import requests
from dotenv import load_dotenv


BASE_URL = "https://api.openalex.org"
REQUEST_TIMEOUT_SECONDS = 15


class OpenAlexAPIError(RuntimeError):
    """Raised when OpenAlex cannot return a usable response."""


load_dotenv()


def reconstruct_abstract(abstract_inverted_index: Optional[dict[str, list[int]]]) -> Optional[str]:
    if not abstract_inverted_index:
        return None

    positioned_words: list[tuple[int, str]] = []
    for word, positions in abstract_inverted_index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned_words.append((position, word))

    if not positioned_words:
        return None
    return " ".join(word for _, word in sorted(positioned_words))


def search_works(
    topic: str,
    limit: int,
    from_year: int | None = 2023,
    sort_by: str = "relevance",
    *,
    page: int = 1,
    page_size: int | None = None,
) -> list[dict[str, Any]]:
    per_page = min(max(page_size if page_size is not None else max(limit * 5, 25), 1), 50)
    params: dict[str, Any] = {
        "search": topic,
        "per-page": per_page,
        "page": max(1, page),
    }

    if from_year:
        params["filter"] = f"from_publication_date:{from_year}-01-01"
    if sort_by == "citations":
        params["sort"] = "cited_by_count:desc"
    elif sort_by == "recent":
        params["sort"] = "publication_date:desc"

    mailto = os.getenv("OPENALEX_EMAIL")
    if mailto:
        params["mailto"] = mailto

    try:
        response = requests.get(f"{BASE_URL}/works", params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OpenAlexAPIError(f"OpenAlex request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenAlexAPIError("OpenAlex returned invalid JSON.") from exc

    results = payload.get("results")
    if not isinstance(results, list):
        raise OpenAlexAPIError("OpenAlex response did not include a results list.")

    works: list[dict[str, Any]] = []
    for work in results:
        if not isinstance(work, dict):
            continue
        normalized_work = dict(work)
        normalized_work["abstract"] = reconstruct_abstract(normalized_work.get("abstract_inverted_index"))
        works.append(normalized_work)
    return works
