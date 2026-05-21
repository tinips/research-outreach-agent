import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import DraftCandidate


DEFAULT_DRAFTS_CSV_PATH = Path("outputs") / "latest" / "drafts.csv"
DEFAULT_DRAFTS_JSON_PATH = Path("outputs") / "latest" / "drafts.json"
DEFAULT_DRAFTS_MD_PATH = Path("outputs") / "latest" / "drafts.md"
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

FIELDNAMES = [
    "candidate_key",
    "person_key",
    "paper_key",
    "candidate_name",
    "group",
    "email",
    "email_confidence",
    "name",
    "institution",
    "paper_title",
    "paper_url",
    "subject",
    "body",
    "draft_body",
    "verification_notes",
]
EMAIL_PRESERVED_FIELDS = {"email", "email_confidence"}


def save_drafts_csv(
    drafts: Iterable[DraftCandidate],
    path: Path = DEFAULT_DRAFTS_CSV_PATH,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for draft in drafts:
            row = _draft_to_dict(draft)
            writer.writerow(
                {
                    field: _sanitize_value(row.get(field), preserve_email=field in EMAIL_PRESERVED_FIELDS)
                    for field in FIELDNAMES
                }
            )

    return path.as_posix()


def archive_existing_drafts_json(
    path: Path = DEFAULT_DRAFTS_JSON_PATH,
    *,
    now: datetime | None = None,
) -> str | None:
    path = Path(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f"Drafts JSON path is not a file: {path}")

    archive_dir = path.parent / "old_drafts"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"drafts_{timestamp}.json"
    suffix = 2
    while archive_path.exists():
        archive_path = archive_dir / f"drafts_{timestamp}_{suffix}.json"
        suffix += 1

    path.replace(archive_path)
    return archive_path.as_posix()


def save_drafts_json(
    drafts: Iterable[DraftCandidate],
    topics: list[str],
    path: Path = DEFAULT_DRAFTS_JSON_PATH,
    notes: list[str] | None = None,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    draft_list = [_sanitize_dict(_draft_to_dict(draft)) for draft in drafts]
    default_notes = [
        "Drafts are editable human-review artifacts only.",
        "No email was sent and no Gmail draft was created.",
    ]
    payload = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "topics": topics,
        "count": len(draft_list),
        "drafts": draft_list,
        "notes": [*default_notes, *(notes or [])],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path.as_posix()


def save_drafts_markdown(
    drafts: Iterable[DraftCandidate],
    topics: list[str],
    path: Path = DEFAULT_DRAFTS_MD_PATH,
    notes: list[str] | None = None,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    draft_list = [_draft_to_dict(draft) for draft in drafts]
    lines = [
        "# Drafts",
        "",
        f"- Run timestamp UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Topics: {', '.join(topics)}",
        f"- Draft count: {len(draft_list)}",
        "- Drafts are editable text only.",
        "- No email was sent and no Gmail draft was created.",
        "",
    ]
    for note in notes or []:
        lines.append(f"- {note}")
    if notes:
        lines.append("")

    for index, draft in enumerate(draft_list, start=1):
        lines.extend(
            [
                f"## Draft {index}",
                "",
                f"- Candidate: {_sanitize_value(draft.get('name')) or 'Unknown candidate'}",
                f"- Institution: {_sanitize_value(draft.get('institution')) or 'Unknown institution'}",
                f"- Paper: {_sanitize_value(draft.get('paper_title')) or 'Unknown paper'}",
                f"- Subject: {_sanitize_value(draft.get('subject'))}",
                "",
                "### Email draft",
                "",
                _sanitize_value(draft.get("draft_body")) or "",
                "",
                "### Verification notes",
                "",
                _sanitize_value(draft.get("verification_notes")) or "",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path.as_posix()


def _draft_to_dict(draft: DraftCandidate) -> dict:
    if hasattr(draft, "model_dump"):
        data = draft.model_dump()
    else:
        data = draft.dict()
    if not data.get("candidate_name"):
        data["candidate_name"] = data.get("name")
    if not data.get("body"):
        data["body"] = data.get("draft_body")
    return data


def _sanitize_dict(data: dict) -> dict:
    return {
        key: _sanitize_value(value, preserve_email=key in EMAIL_PRESERVED_FIELDS)
        for key, value in data.items()
    }


def _sanitize_value(value, *, preserve_email: bool = False):
    if isinstance(value, str):
        if preserve_email:
            return value
        return EMAIL_PATTERN.sub("", value)
    return value
