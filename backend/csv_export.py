import csv
import json
import re
from pathlib import Path
from typing import Iterable

from .models import Candidate


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
DEFAULT_CANDIDATES_CSV_PATH = Path("outputs") / "latest" / "candidates.csv"
FIELDNAMES = [
    "group",
    "source",
    "paper_id",
    "person_key",
    "paper_key",
    "candidate_key",
    "status",
    "seen_status",
    "name",
    "institution",
    "inferred_role",
    "author_url",
    "email",
    "email_source",
    "email_confidence",
    "email_evidence",
    "possible_emails",
    "email_verification_notes",
    "paper_title",
    "paper_year",
    "paper_url",
    "abstract",
    "cited_by_count",
    "opportunity_angle",
    "research_signal_score",
    "outreach_probability_score",
    "contribution_fit_score",
    "lab_signal_score",
    "paper_signal_score",
    "project_activity_score",
    "contactability_score",
    "contribution_angle_score",
    "profile_fit_score",
    "novelty_score",
    "search_signal_score",
    "fit_score",
    "final_score",
    "contact_priority",
    "selection_reason",
    "suggested_outreach_angle",
    "verification_notes",
]


def save_candidates_csv(
    candidates: Iterable[Candidate],
    path: Path = DEFAULT_CANDIDATES_CSV_PATH,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for candidate in candidates:
            row = _candidate_to_dict(candidate)
            writer.writerow({field: _csv_value(field, row.get(field)) for field in FIELDNAMES})
    return path.as_posix()


def _candidate_to_dict(candidate: Candidate) -> dict:
    if hasattr(candidate, "model_dump"):
        return candidate.model_dump()
    return candidate.dict()


def _sanitize_value(value):
    if isinstance(value, str):
        return EMAIL_PATTERN.sub("", value)
    return value


def _csv_value(field: str, value):
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if field in {"email", "email_source", "email_confidence", "email_evidence", "possible_emails", "email_verification_notes"}:
        return value
    return _sanitize_value(value)
