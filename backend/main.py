import re
from typing import Any, Optional

from fastapi import FastAPI, HTTPException

from .csv_export import save_candidates_csv
from .models import Candidate, SearchResearchersRequest, SearchResearchersResponse
from .openalex_client import OpenAlexAPIError, search_works
from .scoring import score_candidate
from .state import attach_tracking


OPPORTUNITY_ANGLE = (
    "Potential research engineering contribution: implementation, experiments, "
    "evaluation, reproducibility, or research tooling."
)
API_VERSION = "0.2-diverse-recent-search"
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MAX_INSTITUTION_LENGTH = 160


app = FastAPI(
    title="Research Outreach Agent API",
    version="0.1.0",
    description="MVP backend for research paper and researcher discovery.",
)


@app.get("/health", operation_id="healthCheck")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version", operation_id="getVersion")
def version() -> dict[str, str]:
    return {"version": API_VERSION}


@app.post(
    "/search_researchers",
    response_model=SearchResearchersResponse,
    operation_id="searchResearchers",
)
def search_researchers(
    request: SearchResearchersRequest,
) -> SearchResearchersResponse:
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="topic is required and cannot be empty")

    limit = min(request.limit, 50)
    max_authors_per_paper = min(request.max_authors_per_paper, 5)

    try:
        works = search_works(
            topic=topic,
            limit=limit,
            from_year=request.from_year,
            sort_by=request.sort_by,
        )
    except OpenAlexAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    candidates = _build_candidates(
        works=works,
        topic=topic,
        limit=limit,
        max_authors_per_paper=max_authors_per_paper,
        from_year=request.from_year,
    )
    csv_path = save_candidates_csv(candidates) if request.save_csv else None

    return SearchResearchersResponse(
        topic=topic,
        limit=limit,
        count=len(candidates),
        candidates=candidates,
        csv_path=csv_path,
    )


def _build_candidates(
    works: list[dict[str, Any]],
    topic: str,
    limit: int,
    max_authors_per_paper: int,
    from_year: int,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen_paper_ids: set[str] = set()
    seen_author_keys: set[str] = set()

    for work in works:
        paper_year = work.get("publication_year")
        if isinstance(paper_year, int) and paper_year < from_year:
            continue

        paper_id = _paper_key(work)
        if not paper_id or paper_id in seen_paper_ids:
            continue
        seen_paper_ids.add(paper_id)

        authors_added_for_paper = 0
        for authorship in _rank_authorships(work.get("authorships") or []):
            if authors_added_for_paper >= max_authors_per_paper:
                break
            if not isinstance(authorship, dict):
                continue

            author = authorship.get("author") or {}
            if not isinstance(author, dict):
                author = {}

            name = author.get("display_name") or authorship.get("raw_author_name")
            if not name:
                continue

            author_id = author.get("id")
            author_key = author_id or _normalize_name(name)
            if not author_key or author_key in seen_author_keys:
                continue

            seen_author_keys.add(author_key)
            institution = _extract_institution(authorship)
            email = _extract_email(authorship)
            paper_url = _extract_paper_url(work)
            scores = score_candidate(
                topic=topic,
                work=work,
                author_url=author_id,
                institution=institution,
                paper_url=paper_url,
            )
            candidate = Candidate(
                name=name,
                institution=institution,
                author_url=author_id,
                email=email,
                email_source="candidate" if email else None,
                source="openalex",
                paper_id=paper_id,
                paper_title=work.get("display_name") or work.get("title"),
                paper_year=work.get("publication_year"),
                paper_url=paper_url,
                abstract=work.get("abstract"),
                cited_by_count=work.get("cited_by_count"),
                opportunity_angle=OPPORTUNITY_ANGLE,
                **scores,
            )
            candidates.append(attach_tracking(candidate))
            authors_added_for_paper += 1

            if len(candidates) >= limit:
                return candidates

    return candidates


def _extract_institution(authorship: dict[str, Any]) -> Optional[str]:
    institutions = authorship.get("institutions") or []
    if institutions:
        first_institution = institutions[0]
        if isinstance(first_institution, dict):
            display_name = first_institution.get("display_name")
            if display_name:
                return _clean_institution(display_name)

    raw_affiliations = authorship.get("raw_affiliation_strings") or []
    if raw_affiliations:
        return _clean_institution(raw_affiliations[0])

    return None


def _extract_email(authorship: dict[str, Any]) -> Optional[str]:
    raw_affiliations = authorship.get("raw_affiliation_strings") or []
    for raw_affiliation in raw_affiliations:
        if not isinstance(raw_affiliation, str):
            continue
        match = EMAIL_PATTERN.search(raw_affiliation)
        if match:
            return match.group(0)
    return None


def _clean_institution(institution: str) -> Optional[str]:
    cleaned = EMAIL_PATTERN.sub("", institution)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = cleaned.strip(" ,;:-")

    if not cleaned:
        return None

    if len(cleaned) > MAX_INSTITUTION_LENGTH:
        cleaned = cleaned[:MAX_INSTITUTION_LENGTH].rsplit(" ", 1)[0].rstrip(" ,;:-")

    return cleaned


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def _paper_key(work: dict[str, Any]) -> Optional[str]:
    return work.get("id") or work.get("doi") or _normalize_name(
        work.get("display_name") or work.get("title") or ""
    )


def _rank_authorships(authorships: list[Any]) -> list[dict[str, Any]]:
    ranked_authorships: list[tuple[int, int, int, int, dict[str, Any]]] = []
    for index, authorship in enumerate(authorships):
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") or {}
        has_author_id = isinstance(author, dict) and bool(author.get("id"))
        has_institution = bool(_extract_institution(authorship))
        position = authorship.get("author_position")
        if position == "first":
            position_rank = 0
        elif position == "middle":
            position_rank = 1
        elif position == "last":
            position_rank = 2
        else:
            position_rank = 3
        ranked_authorships.append(
            (
                0 if has_institution else 1,
                0 if has_author_id else 1,
                position_rank,
                index,
                authorship,
            )
        )

    return [authorship for _, _, _, _, authorship in sorted(ranked_authorships)]


def _extract_paper_url(work: dict[str, Any]) -> Optional[str]:
    if work.get("doi"):
        return work.get("doi")

    primary_location = work.get("primary_location") or {}
    if isinstance(primary_location, dict) and primary_location.get("landing_page_url"):
        return primary_location.get("landing_page_url")

    open_access = work.get("open_access") or {}
    if isinstance(open_access, dict) and open_access.get("oa_url"):
        return open_access.get("oa_url")

    return work.get("id")
