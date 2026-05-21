import argparse
import json
from pathlib import Path

from .cli_search import DEFAULT_OUTPUT_DIR
from .draft_generator import DEFAULT_TEMPLATE_PATH, generate_drafts_from_candidates_json
from .drafts_export import (
    archive_existing_drafts_json,
    save_drafts_csv,
    save_drafts_json,
    save_drafts_markdown,
)


DEFAULT_CANDIDATES_INPUT = DEFAULT_OUTPUT_DIR / "candidates.json"


def add_drafts_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        default=DEFAULT_CANDIDATES_INPUT.as_posix(),
        help=f"Path to candidates JSON. Default: {DEFAULT_CANDIDATES_INPUT.as_posix()}.",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--limit", type=int, help="Maximum number of candidates to draft.")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE_PATH.as_posix(), help="Email template path.")


def run_drafts(args: argparse.Namespace) -> str:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    limit = max(0, args.limit) if args.limit is not None else None

    payload = _load_candidates_payload(input_path)
    topics = payload.get("topics") if isinstance(payload.get("topics"), list) else []
    topics = [str(topic) for topic in topics]

    drafts = generate_drafts_from_candidates_json(
        input_path,
        template_path=args.template,
        limit=limit,
    )
    notes = [
        f"Drafts generated from existing candidates file: {input_path.as_posix()}.",
        "No candidate discovery was run.",
        "No outreach was sent, no Gmail draft was created, and no LinkedIn automation was performed.",
    ]

    drafts_md = save_drafts_markdown(drafts, topics, output_dir / "drafts.md", notes=notes)
    drafts_csv = save_drafts_csv(drafts, output_dir / "drafts.csv")
    archived_drafts = archive_existing_drafts_json(output_dir / "drafts.json")
    if archived_drafts:
        print(f"Archived previous Drafts JSON: {archived_drafts}")
    drafts_json = save_drafts_json(drafts, topics, output_dir / "drafts.json", notes=notes)

    print(f"Loaded candidates JSON: {input_path.as_posix()}")
    print(f"Generated {len(drafts)} deterministic drafts")
    print(f"Drafts Markdown: {drafts_md}")
    print(f"Drafts CSV: {drafts_csv}")
    print(f"Drafts JSON: {drafts_json}")
    return drafts_json


def _load_candidates_payload(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Candidates JSON not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ValueError('Input JSON must be an object with a top-level "candidates" list')
    return payload
