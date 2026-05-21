import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .csv_export import save_candidates_csv
from .draft_generator import generate_drafts
from .drafts_export import (
    archive_existing_drafts_json,
    save_drafts_csv,
    save_drafts_json,
    save_drafts_markdown,
)
from .email_lookup import enrich_candidate_emails
from .markdown_export import save_candidates_markdown
from .models import Candidate
from .openalex_client import search_works
from .scoring import score_candidate
from .state import (
    attach_tracking,
    candidate_seen_status,
    filter_candidates,
    ensure_seen_files,
    load_state,
    novelty_score_for_seen_status,
    write_seen_tracking,
)


LOGGER = logging.getLogger(__name__)
EMAIL_LOOKUP_CANDIDATE_CAP = 6
DEFAULT_OUTPUT_DIR = Path("outputs") / "latest"
DEFAULT_TOPICS = [
    "LLM agents evaluation",
    "AI for science foundation models",
    "multimodal AI agents",
    "robot learning foundation models",
    "AI safety evaluation",
    "data-centric AI benchmark",
    "ML infrastructure for LLMs",
]
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
FILTERS_APPLIED = [
    "seen candidates or papers unless --include-seen",
    "duplicate people",
    "max candidates per institution",
]


def main() -> None:
    raise SystemExit(run())


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_generation(_parse_args(argv))
    return 0


def run_generation(args: argparse.Namespace) -> str:
    topics = _resolve_topics(args)
    output_dir = Path(args.output_dir)
    limit = max(1, args.limit)
    stretch_targets = max(0, args.stretch_targets)
    realistic_targets = max(0, args.realistic_targets)
    if args.top_k is not None and args.stretch_targets == 3 and args.realistic_targets == 3:
        top_k = max(0, args.top_k)
        stretch_targets = max(0, top_k // 2)
        realistic_targets = max(0, top_k - stretch_targets)
    max_authors_per_paper = max(1, min(args.max_authors_per_paper, 5))
    max_candidates_per_institution = max(1, args.max_candidates_per_institution)
    seen_cooldown_days = max(0, args.seen_cooldown_days)
    max_pages = max(1, args.max_pages)
    max_results_scanned = max(1, args.max_results_scanned) if args.max_results_scanned else None
    email_lookup_max_results = max(1, args.email_lookup_max_results)

    ensure_seen_files()
    selected, discovery_pool = search_topics(
        topics=topics,
        limit=limit,
        stretch_targets=stretch_targets,
        realistic_targets=realistic_targets,
        from_year=max(1900, args.from_year),
        sort_by=args.sort_by,
        max_authors_per_paper=max_authors_per_paper,
        max_candidates_per_institution=max_candidates_per_institution,
        seen_cooldown_days=seen_cooldown_days,
        max_pages=max_pages,
        max_results_scanned=max_results_scanned,
        include_seen=args.include_seen,
        top_k=args.top_k,
        email_lookup=args.email_lookup,
        email_lookup_provider=args.email_lookup_provider,
        email_lookup_max_results=email_lookup_max_results,
        return_discovery_pool=True,
    )

    now = datetime.now(timezone.utc)
    write_seen_tracking(
        selected,
        selected_candidate_keys={candidate.candidate_key or "" for candidate in selected},
        now=now,
    )

    csv_path = save_candidates_csv(selected, output_dir / "candidates.csv")
    json_path = save_candidates_json(
        selected,
        topics,
        output_dir / "candidates.json",
        stretch_targets=stretch_targets,
        realistic_targets=realistic_targets,
        seen_cooldown_days=seen_cooldown_days,
    )
    markdown_path = save_candidates_markdown(
        selected,
        topics,
        output_dir / "candidates.md",
        stretch_targets=stretch_targets,
        realistic_targets=realistic_targets,
        seen_cooldown_days=seen_cooldown_days,
        filters_applied=FILTERS_APPLIED,
    )
    draft_notes = [
        "Drafts follow prompts/email_template.md.",
        "This API-free branch does not use the OpenAI API.",
        "No outreach was sent, no Gmail draft was created, and no LinkedIn automation was performed.",
    ]
    drafts = generate_drafts(selected) if args.generate_drafts else []
    if not args.generate_drafts:
        draft_notes.append("Draft generation was disabled for this run.")
    drafts_md = save_drafts_markdown(drafts, topics, output_dir / "drafts.md", notes=draft_notes)
    drafts_csv = save_drafts_csv(drafts, output_dir / "drafts.csv")
    archived_drafts = archive_existing_drafts_json(output_dir / "drafts.json")
    if archived_drafts:
        print(f"Archived previous Drafts JSON: {archived_drafts}")
    drafts_json = save_drafts_json(drafts, topics, output_dir / "drafts.json", notes=draft_notes)

    print(f"Discovered {len(discovery_pool)} candidates")
    print(f"Saved {len(selected)} deterministic candidates")
    print(f"Candidates CSV: {csv_path}")
    print(f"Candidates JSON: {json_path}")
    print(f"Candidates Markdown: {markdown_path}")
    print(f"Generated {len(drafts)} deterministic drafts")
    print(f"Drafts Markdown: {drafts_md}")
    print(f"Drafts CSV: {drafts_csv}")
    print(f"Drafts JSON: {drafts_json}")
    return drafts_json


def search_topics(
    *,
    topics: list[str],
    limit: int,
    stretch_targets: int = 3,
    realistic_targets: int = 3,
    from_year: int,
    sort_by: str,
    max_authors_per_paper: int,
    max_candidates_per_institution: int = 2,
    seen_cooldown_days: int = 60,
    max_pages: int = 5,
    max_results_scanned: Optional[int] = None,
    include_seen: bool = False,
    top_k: Optional[int] = None,
    email_lookup: bool = False,
    email_lookup_provider: str = "serpapi",
    email_lookup_max_results: int = 5,
    return_discovery_pool: bool = False,
) -> list[Candidate] | tuple[list[Candidate], list[Candidate]]:
    if top_k is not None and stretch_targets == 3 and realistic_targets == 3:
        stretch_targets = max(0, top_k // 2)
        realistic_targets = max(0, top_k - stretch_targets)

    state = load_state()
    now = datetime.now(timezone.utc)
    total_requested = stretch_targets + realistic_targets
    per_topic_candidates: list[list[Candidate]] = [[] for _ in topics]
    scanned_results = 0
    discovery_pool: list[Candidate] = []
    selected: list[Candidate] = []

    for page in range(1, max_pages + 1):
        any_results = False
        for index, topic in enumerate(topics):
            if max_results_scanned is not None and scanned_results >= max_results_scanned:
                break

            page_size = limit
            if max_results_scanned is not None:
                page_size = min(page_size, max_results_scanned - scanned_results)
            if page_size <= 0:
                break

            works = search_works(
                topic=topic,
                limit=limit,
                from_year=from_year,
                sort_by=sort_by,
                page=page,
                page_size=page_size,
            )
            scanned_results += len(works)
            any_results = any_results or bool(works)
            topic_candidates = build_candidates(
                works=works,
                topic=topic,
                limit=limit,
                max_authors_per_paper=max_authors_per_paper,
                from_year=from_year,
            )
            per_topic_candidates[index].extend(topic_candidates)
            per_topic_candidates[index].sort(key=lambda candidate: candidate.final_score, reverse=True)

        discovery_pool = _merge_diverse_candidates(
            per_topic_candidates,
            _merged_pool_limit(limit, page=page, topic_count=len(topics), max_results_scanned=max_results_scanned),
            max_authors_per_paper,
        )
        selected = _select_candidates_from_pool(
            discovery_pool,
            state=state,
            now=now,
            seen_cooldown_days=seen_cooldown_days,
            include_seen=include_seen,
            stretch_targets=stretch_targets,
            realistic_targets=realistic_targets,
            max_candidates_per_institution=max_candidates_per_institution,
        )
        if len(selected) >= total_requested:
            break
        if not any_results:
            break
        if max_results_scanned is not None and scanned_results >= max_results_scanned:
            break

    if email_lookup:
        selected = enrich_final_selected_candidate_emails(
            selected,
            provider=email_lookup_provider,
            max_results=email_lookup_max_results,
        )
    selected_by_key = {candidate.candidate_key: candidate for candidate in selected if candidate.candidate_key}
    updated_discovery_pool = [
        selected_by_key.get(candidate.candidate_key, _with_seen_scores(candidate, state=state, seen_cooldown_days=seen_cooldown_days, now=now))
        for candidate in discovery_pool
    ]
    if return_discovery_pool:
        return selected, updated_discovery_pool
    return selected


def enrich_final_selected_candidate_emails(
    selected: list[Candidate],
    *,
    provider: str,
    max_results: int,
) -> list[Candidate]:
    if len(selected) > EMAIL_LOOKUP_CANDIDATE_CAP:
        LOGGER.info("Email lookup: capped at 6 final candidates")
    candidates_for_lookup = selected[:EMAIL_LOOKUP_CANDIDATE_CAP]
    remaining_candidates = selected[EMAIL_LOOKUP_CANDIDATE_CAP:]
    enriched = enrich_candidate_emails(
        candidates_for_lookup,
        enabled=True,
        provider=provider,
        max_results=max_results,
    )
    return enriched + remaining_candidates


def _select_candidates_from_pool(
    discovery_pool: list[Candidate],
    *,
    state: dict,
    now: datetime,
    seen_cooldown_days: int,
    include_seen: bool,
    stretch_targets: int,
    realistic_targets: int,
    max_candidates_per_institution: int,
) -> list[Candidate]:
    eligible = filter_candidates(discovery_pool)
    scored = [
        _with_seen_scores(candidate, state=state, seen_cooldown_days=seen_cooldown_days, now=now)
        for candidate in eligible
    ]
    normal_pool = [
        candidate
        for candidate in scored
        if include_seen or candidate.seen_status != "recently_shortlisted"
    ]
    recent_pool = [] if not include_seen else [
        candidate
        for candidate in scored
        if candidate.seen_status == "recently_shortlisted"
    ]
    return _select_shortlist(
        normal_pool=normal_pool,
        recent_pool=recent_pool,
        stretch_targets=stretch_targets,
        realistic_targets=realistic_targets,
        max_candidates_per_institution=max_candidates_per_institution,
    )


def _merged_pool_limit(
    limit: int,
    *,
    page: int,
    topic_count: int,
    max_results_scanned: Optional[int],
) -> int:
    accumulated_target = max(limit, limit * page * max(1, topic_count))
    if max_results_scanned is None:
        return accumulated_target
    return min(accumulated_target, max_results_scanned)


def build_candidates(
    *,
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
                inferred_role=_infer_role(authorship),
                opportunity_angle=(
                    "Potential research engineering contribution: implementation, experiments, "
                    "evaluation, reproducibility, data pipelines, benchmark runs, or research tooling."
                ),
                **scores,
            )
            candidates.append(attach_tracking(candidate))
            authors_added_for_paper += 1
            if len(candidates) >= limit:
                return candidates
    return candidates


def save_candidates_json(
    candidates: Iterable[Candidate],
    topics: list[str],
    path: Path,
    stretch_targets: int = 3,
    realistic_targets: int = 3,
    seen_cooldown_days: int = 60,
    **_: object,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_list = [_sanitize_candidate(candidate) for candidate in candidates]
    payload = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "topics": topics,
        "stretch_targets_requested": stretch_targets,
        "realistic_targets_requested": realistic_targets,
        "seen_cooldown_days": seen_cooldown_days,
        "count": len(candidate_list),
        "filters_applied": FILTERS_APPLIED,
        "candidates": candidate_list,
        "notes": [
            "Metadata comes from OpenAlex.",
            "This API-free branch does not use the OpenAI API.",
            "No outreach was sent and no Gmail draft was created.",
            "Public email lookup uses SerpAPI by default when SERPAPI_API_KEY is configured.",
            "SerpAPI is used only after final candidate selection and checks at most 6 selected candidates.",
            "Email lookup does not guess emails and does not require institution domains.",
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path.as_posix()


def _select_shortlist(
    *,
    normal_pool: list[Candidate],
    recent_pool: list[Candidate],
    stretch_targets: int,
    realistic_targets: int,
    max_candidates_per_institution: int,
) -> list[Candidate]:
    selected: list[Candidate] = []
    selected_people: set[str] = set()
    selected_papers: set[str] = set()
    institution_counts: dict[str, int] = {}

    def add(candidate: Candidate, group: str, reason: str, fallback_recent: bool = False) -> bool:
        if not _passes_diversity(
            candidate,
            selected_people=selected_people,
            selected_papers=selected_papers,
            institution_counts=institution_counts,
            max_candidates_per_institution=max_candidates_per_institution,
        ):
            return False
        seen_status = "fallback_recently_seen" if fallback_recent else candidate.seen_status
        verification_notes = _verification_notes(candidate, fallback_recent=fallback_recent)
        selected.append(
            _copy_candidate(
                candidate,
                {
                    "group": group,
                    "seen_status": seen_status,
                    "selection_reason": reason,
                    "verification_notes": verification_notes,
                    "status": "shortlisted",
                },
            )
        )
        if candidate.person_key:
            selected_people.add(candidate.person_key)
        if candidate.paper_key:
            selected_papers.add(candidate.paper_key)
        institution_key = _institution_key(candidate.institution)
        if institution_key:
            institution_counts[institution_key] = institution_counts.get(institution_key, 0) + 1
        return True

    stretch_candidates = sorted(
        normal_pool,
        key=lambda candidate: (candidate.research_signal_score, candidate.final_score),
        reverse=True,
    )
    for candidate in stretch_candidates:
        if sum(1 for item in selected if item.group == "stretch") >= stretch_targets:
            break
        add(candidate, "stretch", _selection_reason(candidate, "stretch"))

    realistic_candidates = sorted(
        normal_pool,
        key=lambda candidate: (
            candidate.outreach_probability_score + candidate.contribution_fit_score,
            candidate.final_score,
        ),
        reverse=True,
    )
    for candidate in realistic_candidates:
        if sum(1 for item in selected if item.group == "realistic") >= realistic_targets:
            break
        add(candidate, "realistic", _selection_reason(candidate, "realistic"))

    total_requested = stretch_targets + realistic_targets
    remaining = sorted(normal_pool, key=lambda candidate: candidate.final_score, reverse=True)
    for candidate in remaining:
        if len(selected) >= total_requested:
            break
        add(candidate, "balanced-fill", _selection_reason(candidate, "balanced-fill"))

    recent_remaining = sorted(recent_pool, key=lambda candidate: candidate.final_score, reverse=True)
    for candidate in recent_remaining:
        if len(selected) >= total_requested:
            break
        add(
            candidate,
            "balanced-fill",
            "Last-resort fill because not enough non-recent eligible candidates were available.",
            fallback_recent=True,
        )

    return selected


def _passes_diversity(
    candidate: Candidate,
    *,
    selected_people: set[str],
    selected_papers: set[str],
    institution_counts: dict[str, int],
    max_candidates_per_institution: int,
) -> bool:
    if candidate.person_key and candidate.person_key in selected_people:
        return False
    if candidate.paper_key and candidate.paper_key in selected_papers:
        return False
    institution_key = _institution_key(candidate.institution)
    if institution_key and institution_counts.get(institution_key, 0) >= max_candidates_per_institution:
        return False
    return True


def _with_seen_scores(candidate: Candidate, *, state: dict, seen_cooldown_days: int, now: datetime) -> Candidate:
    seen_status = candidate_seen_status(candidate, state, seen_cooldown_days, now)
    novelty_score = novelty_score_for_seen_status(seen_status)
    final_score = _final_score(
        research_signal_score=candidate.research_signal_score,
        outreach_probability_score=candidate.outreach_probability_score,
        project_activity_score=candidate.project_activity_score,
        contribution_fit_score=candidate.contribution_fit_score,
        novelty_score=novelty_score,
    )
    return _copy_candidate(
        candidate,
        {
            "seen_status": seen_status,
            "novelty_score": novelty_score,
            "final_score": final_score,
            "fit_score": final_score,
            "contact_priority": _contact_priority(final_score),
            "verification_notes": _verification_notes(candidate, fallback_recent=False),
        },
    )


def _selection_reason(candidate: Candidate, group: str) -> str:
    if group == "stretch":
        return (
            "High research signal from paper quality, institution/lab signal, recency, relevance, or influence; "
            "response probability may be lower."
        )
    if group == "realistic":
        return (
            "Good outreach probability and contribution fit for implementation, experiments, evaluation, "
            "reproducibility, data pipelines, benchmark runs, or research tooling."
        )
    return "Balanced/fallback candidate selected to preserve a six-candidate shortlist with diversity constraints."


def _verification_notes(candidate: Candidate, *, fallback_recent: bool) -> str:
    notes = [
        "Metadata comes from OpenAlex.",
        "No outreach was sent and no Gmail draft was created.",
        "Public email lookup uses SerpAPI by default when SERPAPI_API_KEY is configured.",
        "SerpAPI is used only after final candidate selection and checks at most 6 selected candidates.",
        "Email lookup does not guess emails and does not require institution domains.",
        "Verify the paper, author, institution, role, and best contact path before drafting outreach.",
    ]
    if fallback_recent:
        notes.append(
            "Fallback: this candidate or paper was recently shortlisted, but not enough alternatives were available."
        )
    elif candidate.seen_status == "recently_shortlisted":
        notes.append("Recently shortlisted; excluded from normal selection unless fallback is required.")
    return " ".join(notes)


def _merge_diverse_candidates(
    candidate_groups: list[list[Candidate]],
    limit: int,
    max_authors_per_paper: int,
) -> list[Candidate]:
    merged: list[Candidate] = []
    paper_counts: dict[str, int] = {}
    seen_author_keys: set[str] = set()
    max_group_size = max((len(group) for group in candidate_groups), default=0)

    for index in range(max_group_size):
        for group in candidate_groups:
            if index >= len(group):
                continue
            candidate = group[index]
            paper_key = candidate.paper_key or candidate.paper_id or candidate.paper_url or candidate.paper_title
            author_key = candidate.person_key or candidate.author_url or _normalize_name(candidate.name)
            if author_key in seen_author_keys:
                continue
            if paper_key and paper_counts.get(paper_key, 0) >= max_authors_per_paper:
                continue

            if paper_key:
                paper_counts[paper_key] = paper_counts.get(paper_key, 0) + 1
            if author_key:
                seen_author_keys.add(author_key)

            merged.append(candidate)
            if len(merged) >= limit:
                return merged
    return merged


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic OpenAlex discovery for outreach candidates.")
    add_generation_arguments(parser)
    return parser


def add_generation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--topic", help="Single topic to search.")
    parser.add_argument("--topics", nargs="+", help="Multiple topics to search.")
    parser.add_argument("--limit", type=int, default=40, help="Discovery pool size before final shortlist.")
    parser.add_argument("--top-k", type=int, help="Deprecated compatibility alias for total shortlist size.")
    parser.add_argument("--stretch-targets", type=int, default=3, help="Number of stretch candidates to write.")
    parser.add_argument("--realistic-targets", type=int, default=3, help="Number of realistic candidates to write.")
    parser.add_argument("--from-year", type=int, default=2023, help="Earliest publication year.")
    parser.add_argument("--sort-by", choices=["relevance", "citations", "recent"], default="relevance")
    parser.add_argument("--max-authors-per-paper", type=int, default=1)
    parser.add_argument("--max-candidates-per-institution", type=int, default=2)
    parser.add_argument("--seen-cooldown-days", type=int, default=60)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--max-results-scanned", type=int)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--include-seen", action="store_true")
    parser.add_argument(
        "--email-lookup",
        dest="email_lookup",
        action="store_true",
        help="Enrich final selected candidates with public emails. Enabled by default in the CLI.",
    )
    parser.add_argument(
        "--no-email-lookup",
        dest="email_lookup",
        action="store_false",
        help="Disable public email lookup for this run.",
    )
    parser.add_argument("--email-lookup-provider", choices=["serpapi"], default="serpapi")
    parser.add_argument("--email-lookup-max-results", type=int, default=5)
    parser.add_argument(
        "--generate-drafts",
        dest="generate_drafts",
        action="store_true",
        help="Generate deterministic editable drafts after candidate selection. Enabled by default.",
    )
    parser.add_argument(
        "--no-generate-drafts",
        dest="generate_drafts",
        action="store_false",
        help="Write empty draft outputs instead of deterministic editable drafts.",
    )
    parser.set_defaults(email_lookup=True)
    parser.set_defaults(generate_drafts=True)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _resolve_topics(args: argparse.Namespace) -> list[str]:
    topics: list[str] = []
    if args.topic:
        topics.append(args.topic)
    if args.topics:
        topics.extend(args.topics)
    if not topics:
        topics = DEFAULT_TOPICS
    topics = [topic.strip() for topic in topics if topic and topic.strip()]
    if not topics:
        raise SystemExit("Provide --topic or --topics.")
    return topics


def _sanitize_candidate(candidate: Candidate) -> dict:
    if hasattr(candidate, "model_dump"):
        data = candidate.model_dump()
    else:
        data = candidate.dict()
    return {key: _sanitize_candidate_value(key, value) for key, value in data.items()}


def _sanitize_value(value):
    if isinstance(value, str):
        return EMAIL_PATTERN.sub("", value)
    return value


def _sanitize_candidate_value(key: str, value):
    if key in {"email", "email_source", "email_confidence", "email_evidence", "possible_emails", "email_verification_notes"}:
        return value
    return _sanitize_value(value)


def _extract_institution(authorship: dict[str, Any]) -> Optional[str]:
    institutions = authorship.get("institutions") or []
    if institutions:
        first_institution = institutions[0]
        if isinstance(first_institution, dict) and first_institution.get("display_name"):
            return _clean_institution(first_institution.get("display_name"))
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
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned).strip(" ,;:-")
    if not cleaned:
        return None
    if len(cleaned) > 160:
        cleaned = cleaned[:160].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cleaned


def _paper_key(work: dict[str, Any]) -> Optional[str]:
    return work.get("id") or work.get("doi") or _normalize_name(work.get("display_name") or work.get("title") or "")


def _rank_authorships(authorships: list[Any]) -> list[dict[str, Any]]:
    ranked_authorships: list[tuple[int, int, int, dict[str, Any]]] = []
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
            (0 if has_institution else 1, 0 if has_author_id else 1, position_rank, index, authorship)
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


def _infer_role(authorship: dict[str, Any]) -> str:
    role = authorship.get("author_position")
    if role == "first":
        return "first author; exact role unknown"
    if role == "last":
        return "senior/last author; exact role unknown"
    if role == "middle":
        return "co-author; exact role unknown"
    return "unknown"


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def _institution_key(institution: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (institution or "").lower()).strip("-")


def _copy_candidate(candidate: Candidate, update: dict) -> Candidate:
    if hasattr(candidate, "model_copy"):
        return candidate.model_copy(update=update)
    return candidate.copy(update=update)


def _final_score(
    *,
    research_signal_score: float,
    outreach_probability_score: float,
    project_activity_score: float,
    contribution_fit_score: float,
    novelty_score: float,
) -> float:
    return round(
        (0.25 * research_signal_score)
        + (0.25 * outreach_probability_score)
        + (0.15 * project_activity_score)
        + (0.20 * contribution_fit_score)
        + (0.15 * novelty_score),
        3,
    )


def _contact_priority(final_score: float) -> str:
    if final_score >= 0.70:
        return "high"
    if final_score >= 0.45:
        return "medium"
    return "low"


if __name__ == "__main__":
    main()
