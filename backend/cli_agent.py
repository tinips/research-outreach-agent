import argparse
from pathlib import Path

from .cli_search import DEFAULT_OUTPUT_DIR, save_candidates_json, search_topics
from .csv_export import save_candidates_csv
from .markdown_export import save_candidates_markdown, save_drafts_markdown
from .state import mark_candidates_drafted


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
    if not candidates:
        print("No new candidates after contact/draft filtering.")
        print("Existing output files were left unchanged.")
        return

    drafted_candidates = mark_candidates_drafted(candidates)

    csv_path = save_candidates_csv(drafted_candidates, output_dir / "candidates.csv")
    json_path = save_candidates_json(drafted_candidates, topics, output_dir / "candidates.json")
    markdown_path = save_candidates_markdown(drafted_candidates, topics, output_dir / "candidates.md")
    drafts_path = save_drafts_markdown(drafted_candidates, topics, output_dir / "drafts.md")

    print(f"Drafted {len(drafted_candidates)} candidates")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    print(f"Drafts: {drafts_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search OpenAlex, export candidates, and create editable draft skeletons.",
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
        help="Directory for candidates and drafts output files.",
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


if __name__ == "__main__":
    main()
