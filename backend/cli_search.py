import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .csv_export import save_candidates_csv
from .main import _build_candidates
from .markdown_export import save_candidates_markdown
from .models import Candidate
from .openalex_client import search_works
from .state import filter_candidates


DEFAULT_OUTPUT_DIR = Path("outputs") / "latest"
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def main() -> None:
    args = _parse_args()
    topics = _resolve_topics(args)
    output_dir = Path(args.output_dir)
    limit = max(1, args.limit)
    max_authors_per_paper = max(1, min(args.max_authors_per_paper, 5))

    candidates = search_topics(
        topics=topics,
        limit=limit,
        from_year=max(1900, args.from_year),
        sort_by=args.sort_by,
        max_authors_per_paper=max_authors_per_paper,
        include_drafted=args.include_drafted,
        include_contacted=args.include_contacted,
    )

    csv_path = save_candidates_csv(candidates, output_dir / "candidates.csv")
    json_path = save_candidates_json(candidates, topics, output_dir / "candidates.json")
    markdown_path = save_candidates_markdown(candidates, topics, output_dir / "candidates.md")

    print(f"Saved {len(candidates)} candidates")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")


def search_topics(
    *,
    topics: list[str],
    limit: int,
    from_year: int,
    sort_by: str,
    max_authors_per_paper: int,
    include_drafted: bool = False,
    include_contacted: bool = False,
) -> list[Candidate]:
    per_topic_candidates: list[list[Candidate]] = []

    for topic in topics:
        works = search_works(
            topic=topic,
            limit=limit,
            from_year=from_year,
            sort_by=sort_by,
        )
        topic_candidates = _build_candidates(
            works=works,
            topic=topic,
            limit=limit,
            max_authors_per_paper=max_authors_per_paper,
            from_year=from_year,
        )
        per_topic_candidates.append(
            sorted(topic_candidates, key=lambda candidate: candidate.search_signal_score, reverse=True)
        )

    merged_candidates = _merge_diverse_candidates(per_topic_candidates, limit, max_authors_per_paper)
    return filter_candidates(
        merged_candidates,
        include_drafted=include_drafted,
        include_contacted=include_contacted,
    )


def save_candidates_json(
    candidates: Iterable[Candidate],
    topics: list[str],
    path: Path,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_list = [_sanitize_candidate(candidate) for candidate in candidates]
    payload = {
        "search_datetime_utc": datetime.now(timezone.utc).isoformat(),
        "topics": topics,
        "count": len(candidate_list),
        "candidates": candidate_list,
        "notes": [
            "Metadata comes from OpenAlex.",
            "No email extraction, website scraping, LinkedIn automation, or outreach sending was performed.",
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path.as_posix()


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
            paper_key = candidate.paper_id or candidate.paper_url or candidate.paper_title
            author_key = candidate.author_url or _normalize_name(candidate.name)
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search OpenAlex for broad AI research outreach candidates.",
    )
    parser.add_argument("--topic", help="Single topic to search.")
    parser.add_argument("--topics", nargs="+", help="Multiple topics to search.")
    parser.add_argument("--limit", type=int, default=20, help="Total candidate limit.")
    parser.add_argument("--from-year", type=int, default=2023, help="Earliest publication year.")
    parser.add_argument(
        "--sort-by",
        choices=["relevance", "citations", "recent"],
        default="relevance",
        help="OpenAlex sorting strategy.",
    )
    parser.add_argument(
        "--max-authors-per-paper",
        type=int,
        default=1,
        help="Maximum candidate authors to keep per paper.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR.as_posix(),
        help="Directory for candidates.csv, candidates.json, and candidates.md.",
    )
    parser.add_argument(
        "--include-drafted",
        action="store_true",
        help="Include candidates already marked as drafted.",
    )
    parser.add_argument(
        "--include-contacted",
        action="store_true",
        help="Include candidates already marked as contacted or already used for outreach.",
    )
    return parser.parse_args()


def _resolve_topics(args: argparse.Namespace) -> list[str]:
    topics: list[str] = []
    if args.topic:
        topics.append(args.topic)
    if args.topics:
        topics.extend(args.topics)

    topics = [topic.strip() for topic in topics if topic and topic.strip()]
    if not topics:
        raise SystemExit("Provide --topic or --topics.")

    return topics


def _sanitize_candidate(candidate: Candidate) -> dict:
    if hasattr(candidate, "model_dump"):
        data = candidate.model_dump()
    else:
        data = candidate.dict()
    return {key: _sanitize_value(value) for key, value in data.items()}


def _sanitize_value(value):
    if isinstance(value, str):
        return EMAIL_PATTERN.sub("", value)
    return value


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


if __name__ == "__main__":
    main()
