import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import Candidate


DATA_DIR = Path("data")

SEEN_CANDIDATES_FIELDS = [
    "candidate_key",
    "person_key",
    "paper_key",
    "name",
    "institution",
    "paper_title",
    "paper_url",
    "first_seen_at",
    "last_seen_at",
    "times_seen",
    "last_score",
    "last_group",
    "status",
    "notes",
]


def attach_tracking(candidate: Candidate, status: Optional[str] = None) -> Candidate:
    person_key = build_person_key(candidate)
    paper_key = build_paper_key(candidate)
    return _copy_candidate(
        candidate,
        {
            "person_key": person_key,
            "paper_key": paper_key,
            "candidate_key": build_candidate_key(person_key, paper_key),
            "status": status or candidate.status or "new",
        },
    )


def filter_candidates(
    candidates: Iterable[Candidate],
    *,
    data_dir: Path = DATA_DIR,
) -> list[Candidate]:
    return [attach_tracking(candidate) for candidate in candidates]


def load_state(data_dir: Path = DATA_DIR) -> dict:
    seen_rows = _read_csv(data_dir / "seen_candidates.csv")
    seen_candidates = {
        row["candidate_key"]: row
        for row in seen_rows
        if row.get("candidate_key")
    }
    seen_papers: dict[str, dict[str, str]] = {}
    for row in seen_rows:
        paper_key = row.get("paper_key")
        if not paper_key:
            continue
        existing = seen_papers.get(paper_key)
        if not existing:
            seen_papers[paper_key] = row
            continue
        existing_seen = existing.get("last_seen_at") or existing.get("first_seen_at") or ""
        current_seen = row.get("last_seen_at") or row.get("first_seen_at") or ""
        if current_seen >= existing_seen:
            seen_papers[paper_key] = row
    return {
        "seen_candidates": seen_candidates,
        "seen_papers": seen_papers,
    }


def ensure_tracking_files(data_dir: Path = DATA_DIR) -> None:
    _ensure_csv(data_dir / "seen_candidates.csv", SEEN_CANDIDATES_FIELDS)


def ensure_state_files(data_dir: Path = DATA_DIR) -> None:
    ensure_tracking_files(data_dir)


def ensure_seen_files(data_dir: Path = DATA_DIR) -> None:
    _ensure_csv(data_dir / "seen_candidates.csv", SEEN_CANDIDATES_FIELDS)


def recently_shortlisted(row: Optional[dict[str, str]], cooldown_days: int, now: datetime) -> bool:
    if not row:
        return False
    was_shortlisted = _is_shortlisted_row(row)
    if not was_shortlisted:
        return False
    last_seen = _parse_datetime(row.get("last_seen_at") or row.get("first_seen_at"))
    if not last_seen:
        return False
    return (now - last_seen).days < cooldown_days


def candidate_seen_status(candidate: Candidate, state: dict, cooldown_days: int, now: datetime) -> str:
    candidate_row = state["seen_candidates"].get(candidate.candidate_key or "")
    paper_row = state["seen_papers"].get(candidate.paper_key or "")
    if recently_shortlisted(candidate_row, cooldown_days, now) or recently_shortlisted(
        paper_row,
        cooldown_days,
        now,
    ):
        return "recently_shortlisted"
    if _is_shortlisted_row(candidate_row) or _is_shortlisted_row(paper_row):
        return "seen_before"
    return "new"


def novelty_score_for_seen_status(seen_status: str) -> float:
    if seen_status == "new":
        return 1.0
    if seen_status == "seen_before":
        return 0.7
    if seen_status == "fallback_recently_seen":
        return 0.25
    return 0.15


def write_seen_tracking(
    candidates: Iterable[Candidate],
    *,
    selected_candidate_keys: set[str],
    data_dir: Path = DATA_DIR,
    now: Optional[datetime] = None,
) -> None:
    ensure_seen_files(data_dir)
    candidate_list = list(candidates)
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    candidate_rows = {
        row["candidate_key"]: row
        for row in _read_csv(data_dir / "seen_candidates.csv")
        if row.get("candidate_key")
    }

    for candidate in candidate_list:
        candidate_key = candidate.candidate_key or ""
        if candidate_key:
            row = candidate_rows.get(candidate_key, {})
            candidate_rows[candidate_key] = {
                "candidate_key": candidate_key,
                "person_key": candidate.person_key or "",
                "paper_key": candidate.paper_key or "",
                "name": candidate.name,
                "institution": candidate.institution or "",
                "paper_title": candidate.paper_title or "",
                "paper_url": candidate.paper_url or "",
                "first_seen_at": row.get("first_seen_at") or timestamp,
                "last_seen_at": timestamp,
                "times_seen": str(_increment(row.get("times_seen"))),
                "last_score": _format_score(candidate.final_score),
                "last_group": candidate.group if candidate_key in selected_candidate_keys else row.get("last_group", ""),
                "status": "shortlisted" if candidate_key in selected_candidate_keys else "seen",
                "notes": candidate.verification_notes or row.get("notes", ""),
            }

    _write_csv(data_dir / "seen_candidates.csv", SEEN_CANDIDATES_FIELDS, candidate_rows.values())


def build_person_key(candidate: Candidate) -> str:
    if candidate.author_url:
        openalex_key = _openalex_key(candidate.author_url)
        if openalex_key:
            return openalex_key
        return f"url:{_normalize(candidate.author_url)}"
    return f"name:{_normalize(candidate.name)}|institution:{_normalize(candidate.institution or '')}"


def build_paper_key(candidate: Candidate) -> str:
    if candidate.paper_id:
        openalex_key = _openalex_key(candidate.paper_id)
        if openalex_key:
            return openalex_key
        return f"id:{_normalize(candidate.paper_id)}"
    if candidate.paper_url:
        openalex_key = _openalex_key(candidate.paper_url)
        if openalex_key:
            return openalex_key
        return f"url:{_normalize(candidate.paper_url)}"
    return f"title:{_normalize(candidate.paper_title or '')}|year:{candidate.paper_year or ''}"


def build_candidate_key(person_key: str, paper_key: str) -> str:
    return f"{person_key}::{paper_key}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_rows = sorted(rows, key=lambda row: row.get(fieldnames[0], ""))
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in ordered_rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _ensure_csv(path: Path, fieldnames: list[str]) -> None:
    if path.exists():
        return
    _write_csv(path, fieldnames, [])


def _copy_candidate(candidate: Candidate, update: dict) -> Candidate:
    if hasattr(candidate, "model_copy"):
        return candidate.model_copy(update=update)
    return candidate.copy(update=update)


def _openalex_key(value: str) -> Optional[str]:
    match = re.search(r"openalex\.org/([A-Za-z]\d+)", value)
    if match:
        return f"openalex:{match.group(1)}"
    if re.fullmatch(r"[A-Za-z]\d+", value):
        return f"openalex:{value}"
    return None


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _increment(value: Optional[str]) -> int:
    try:
        return int(value or "0") + 1
    except ValueError:
        return 1


def _format_score(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


def _is_shortlisted_row(row: Optional[dict[str, str]]) -> bool:
    if not row:
        return False
    return row.get("status") == "shortlisted" or bool(row.get("last_group"))
