import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import Candidate


DEFAULT_MARKDOWN_PATH = Path("outputs") / "latest" / "candidates.md"
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def save_candidates_markdown(
    candidates: Iterable[Candidate],
    topics: list[str],
    path: Path = DEFAULT_MARKDOWN_PATH,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_list = list(candidates)

    lines = [
        "# Research Outreach Candidates",
        "",
        f"- Search datetime UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Topics used: {', '.join(topics)}",
        f"- Candidate count: {len(candidate_list)}",
        "- Email extraction: not performed",
        "- Outreach status: no emails sent",
        "",
    ]

    for index, candidate in enumerate(candidate_list, start=1):
        lines.extend(_candidate_section(index, candidate))

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path.as_posix()


def _candidate_section(index: int, candidate: Candidate) -> list[str]:
    data = _candidate_to_dict(candidate)
    name = _clean(data.get("name")) or "Unknown candidate"
    person_key = _clean(data.get("person_key")) or "missing"
    paper_key = _clean(data.get("paper_key")) or "missing"
    candidate_key = _clean(data.get("candidate_key")) or "missing"
    status = _clean(data.get("status")) or "new"
    institution = _clean(data.get("institution")) or "Unknown institution"
    paper_title = _clean(data.get("paper_title")) or "Unknown paper"
    paper_year = data.get("paper_year") or "Unknown year"
    paper_url = _clean(data.get("paper_url")) or "No paper URL available"
    cited_by_count = data.get("cited_by_count")
    source = _clean(data.get("source")) or "openalex"

    return [
        f"## {index}. {name}",
        "",
        f"- Contact name: {name}",
        f"- Person key: {person_key}",
        f"- Paper key: {paper_key}",
        f"- Candidate key: {candidate_key}",
        f"- Status: {status}",
        f"- Institution: {institution}",
        f"- Paper title: {paper_title}",
        f"- Year: {paper_year}",
        f"- Paper URL: {paper_url}",
        f"- Cited by count: {cited_by_count}",
        f"- Source: {source}",
        f"- Contact priority: {_clean(data.get('contact_priority'))}",
        "",
        "### Scores",
        "",
        f"- Lab signal: {data.get('lab_signal_score')}",
        f"- Paper signal: {data.get('paper_signal_score')}",
        f"- Project activity: {data.get('project_activity_score')}",
        f"- Contactability: {data.get('contactability_score')}",
        f"- Contribution angle: {data.get('contribution_angle_score')}",
        f"- Profile fit: {data.get('profile_fit_score')}",
        f"- Search signal: {data.get('search_signal_score')}",
        f"- Fit score: {data.get('fit_score')}",
        "",
        "### Why Interesting",
        "",
        _why_interesting(data),
        "",
        "### Opportunity Angle",
        "",
        _clean(data.get("opportunity_angle")),
        "",
        "### Suggested Outreach Angle",
        "",
        _clean(data.get("suggested_outreach_angle")),
        "",
        "### Verification Notes",
        "",
        "- Metadata comes from OpenAlex.",
        "- No email extraction, website scraping, LinkedIn automation, or outreach sending was performed.",
        "- Verify the paper, author, institution, and best contact path before drafting outreach.",
        "- If outreach is sent manually, update the contact tracking CSVs with `backend.mark_contacted`.",
        "",
    ]


def save_drafts_markdown(
    candidates: Iterable[Candidate],
    topics: list[str],
    path: Path = Path("outputs") / "latest" / "drafts.md",
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_list = list(candidates)

    lines = [
        "# Drafted Outreach Candidates",
        "",
        f"- Draft datetime UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Topics used: {', '.join(topics)}",
        f"- Draft count: {len(candidate_list)}",
        "- Outreach status: drafts generated only; no emails sent",
        "",
    ]

    for index, candidate in enumerate(candidate_list, start=1):
        lines.extend(_draft_section(index, candidate))

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path.as_posix()


def _draft_section(index: int, candidate: Candidate) -> list[str]:
    data = _candidate_to_dict(candidate)
    name = _clean(data.get("name")) or "Unknown candidate"
    institution = _clean(data.get("institution")) or "Unknown institution"
    paper_title = _clean(data.get("paper_title")) or "Unknown paper"
    suggested_angle = _clean(data.get("suggested_outreach_angle"))
    paper_url = _clean(data.get("paper_url")) or "No paper URL available"

    return [
        f"## {index}. {name}",
        "",
        f"- Person key: {_clean(data.get('person_key')) or 'missing'}",
        f"- Paper key: {_clean(data.get('paper_key')) or 'missing'}",
        f"- Candidate key: {_clean(data.get('candidate_key')) or 'missing'}",
        f"- Status: {_clean(data.get('status')) or 'drafted'}",
        f"- Institution: {institution}",
        f"- Paper title: {paper_title}",
        f"- Paper URL: {paper_url}",
        f"- Contact priority: {_clean(data.get('contact_priority'))}",
        "",
        "### Draft Skeleton",
        "",
        f"Subject: Research engineering collaboration on {paper_title}",
        "",
        f"Hi/Dear {name},",
        "",
        "I am a Data Engineering student and AI Research Intern at EPFL LASA Lab, "
        "where I worked on PyTorch-based research code, synthetic data generation, "
        "trajectory evaluation, and reproducible experimental pipelines.",
        "",
        f"I came across your work on \"{paper_title}\" and was especially interested "
        "in the technical direction of the project.",
        "",
        "I am looking for a small remote research engineering collaboration where I "
        "could contribute a few hours per week.",
        "",
        f"{suggested_angle}",
        "",
        "My GitHub: https://github.com/tinips",
        "My CV: attached CV",
        "LinkedIn: https://www.linkedin.com/in/albert-arboles/?skipRedirect=true",
        "",
        "Would you be open to a short conversation, or is there someone in your group I should contact?",
        "",
        "Best,",
        "Albert",
        "",
        "### Verification Notes",
        "",
        "- This is an editable draft skeleton only.",
        "- No email was sent and no Gmail draft was created.",
        "- Verify the paper, author, affiliation, and contact route before using.",
        "- After manually sending, run `python -m backend.mark_contacted ...`.",
        "",
    ]


def _why_interesting(data: dict) -> str:
    title = _clean(data.get("paper_title")) or "this paper"
    cited_by_count = data.get("cited_by_count")
    year = data.get("paper_year")
    return (
        f"{title} appears relevant because it is a {year} AI paper with "
        f"{cited_by_count} OpenAlex citations and a search signal score of "
        f"{data.get('search_signal_score')}."
    )


def _candidate_to_dict(candidate: Candidate) -> dict:
    if hasattr(candidate, "model_dump"):
        return candidate.model_dump()
    return candidate.dict()


def _clean(value) -> str:
    if value is None:
        return ""
    return EMAIL_PATTERN.sub("", str(value)).strip()
