import csv
import re
from pathlib import Path
from typing import Iterable

from .models import Candidate


DEFAULT_CSV_PATH = Path("outputs") / "candidates.csv"
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


FIELDNAMES = [
    "source",
    "paper_id",
    "person_key",
    "paper_key",
    "candidate_key",
    "status",
    "name",
    "institution",
    "author_url",
    "paper_title",
    "paper_year",
    "paper_url",
    "abstract",
    "cited_by_count",
    "opportunity_angle",
    "lab_signal_score",
    "paper_signal_score",
    "project_activity_score",
    "contactability_score",
    "contribution_angle_score",
    "profile_fit_score",
    "search_signal_score",
    "fit_score",
    "contact_priority",
    "suggested_outreach_angle",
]


def save_candidates_csv(
    candidates: Iterable[Candidate],
    path: Path = DEFAULT_CSV_PATH,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for candidate in candidates:
            row = _candidate_to_dict(candidate)
            writer.writerow({field: _sanitize_csv_value(row.get(field)) for field in FIELDNAMES})

    return path.as_posix()


def _candidate_to_dict(candidate: Candidate) -> dict:
    if hasattr(candidate, "model_dump"):
        return candidate.model_dump()
    return candidate.dict()


def _sanitize_csv_value(value):
    if isinstance(value, str):
        return EMAIL_PATTERN.sub("", value)
    return value
