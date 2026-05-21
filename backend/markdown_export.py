import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import Candidate


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def save_candidates_markdown(
    candidates: Iterable[Candidate],
    topics: list[str],
    path: Path,
    stretch_targets: int = 3,
    realistic_targets: int = 3,
    seen_cooldown_days: int = 60,
    filters_applied: list[str] | None = None,
    **_: object,
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_list = list(candidates)
    stretch = [candidate for candidate in candidate_list if candidate.group == "stretch"]
    realistic = [candidate for candidate in candidate_list if candidate.group == "realistic"]
    fallback = [candidate for candidate in candidate_list if candidate.group == "balanced-fill"]
    lines = [
        "# Today’s Research Outreach Candidates",
        "",
        "## Summary",
        "",
        f"- Run timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"- Topics: {', '.join(topics)}",
        f"- Stretch targets requested: {stretch_targets}",
        f"- Realistic targets requested: {realistic_targets}",
        f"- Total selected: {len(candidate_list)}",
        f"- Seen cooldown days: {seen_cooldown_days}",
        f"- Filters applied: {'; '.join(filters_applied or _default_filters())}",
        "",
    ]

    if not candidate_list:
        lines.extend(
            [
                "No eligible candidates were found after scoring, deduplication, and tracking filters.",
                "",
            ]
        )

    lines.extend(["## High-signal stretch targets", ""])
    if stretch:
        for index, candidate in enumerate(stretch, start=1):
            lines.extend(_candidate_section(index, candidate))
    else:
        lines.extend(["No stretch candidates selected.", ""])

    lines.extend(["## Realistic outreach targets", ""])
    if realistic:
        for index, candidate in enumerate(realistic, start=1):
            lines.extend(_candidate_section(index, candidate))
    else:
        lines.extend(["No realistic candidates selected.", ""])

    if fallback:
        lines.extend(["## Balanced/fallback candidates", ""])
        for index, candidate in enumerate(fallback, start=1):
            lines.extend(_candidate_section(index, candidate))

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path.as_posix()


def save_drafts_markdown(drafts: Iterable[object], topics: list[str], path: Path, notes: list[str] | None = None) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    draft_list = list(drafts)
    lines = [
        "# Drafts",
        "",
        f"- Run timestamp UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Topics: {', '.join(topics)}",
        f"- Draft count: {len(draft_list)}",
        "- No email was sent and no Gmail draft was created.",
        "",
    ]
    for note in notes or []:
        lines.append(f"- {note}")
    if notes:
        lines.append("")
    for index, draft in enumerate(draft_list, start=1):
        data = draft.model_dump() if hasattr(draft, "model_dump") else draft.dict()
        lines.extend(
            [
                f"## {index}. {_clean(data.get('name')) or 'Unknown candidate'}",
                "",
                f"- Candidate key: {_clean(data.get('candidate_key'))}",
                f"- Subject: {_clean(data.get('subject'))}",
                "",
                _clean(data.get("draft_body")),
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path.as_posix()


def _candidate_section(index: int, candidate: Candidate) -> list[str]:
    data = _candidate_to_dict(candidate)
    name = _clean(data.get("name")) or "Unknown candidate"
    institution = _clean(data.get("institution")) or "Unknown institution"
    paper_title = _clean(data.get("paper_title")) or "Unknown paper"
    paper_year = data.get("paper_year") or "Unknown year"
    paper_url = _clean(data.get("paper_url")) or "No paper URL available"
    email = _email(data.get("email")) or "not found"
    email_source = _clean(data.get("email_source")) or "unknown"
    email_confidence = _clean(data.get("email_confidence")) or "not_checked"
    email_evidence = _email_text(data.get("email_evidence")) or "none"
    possible_emails = _format_possible_emails(data.get("possible_emails"))
    email_verification_notes = _email_text(data.get("email_verification_notes")) or "Email lookup not requested."
    source = _clean(data.get("source")) or "openalex"
    group = _clean(data.get("group")) or "balanced"
    verification_notes = _clean(data.get("verification_notes")) or (
        "Metadata comes from OpenAlex. Verify the paper, author, institution, and best contact path before drafting."
    )

    return [
        f"### {index}. {name}",
        "",
        f"- group: {group}",
        f"- candidate_key: {_clean(data.get('candidate_key')) or 'missing'}",
        f"- person_key: {_clean(data.get('person_key')) or 'missing'}",
        f"- paper_key: {_clean(data.get('paper_key')) or 'missing'}",
        f"- name: {name}",
        f"- institution: {institution}",
        f"- inferred role: {_clean(data.get('inferred_role')) or 'unknown'}",
        f"- source: {source}",
        f"- email: {email}",
        f"- email source: {email_source}",
        f"- email confidence: {email_confidence}",
        f"- email evidence: {email_evidence}",
        f"- possible emails: {possible_emails}",
        f"- email verification notes: {email_verification_notes}",
        f"- paper title: {paper_title}",
        f"- paper year: {paper_year}",
        f"- paper URL: {paper_url}",
        f"- research_signal_score: {data.get('research_signal_score')}",
        f"- outreach_probability_score: {data.get('outreach_probability_score')}",
        f"- contribution_fit_score: {data.get('contribution_fit_score')}",
        f"- project_activity_score: {data.get('project_activity_score')}",
        f"- novelty_score: {data.get('novelty_score')}",
        f"- final_score: {data.get('final_score')}",
        f"- contact priority: {_clean(data.get('contact_priority'))}",
        f"- why this is a stretch or realistic target: {_clean(data.get('selection_reason'))}",
        f"- opportunity angle: {_clean(data.get('opportunity_angle'))}",
        f"- suggested outreach angle: {_clean(data.get('suggested_outreach_angle'))}",
        f"- verification notes: {verification_notes}",
        f"- seen status: {_clean(data.get('seen_status')) or 'new'}",
        "",
    ]


def _candidate_to_dict(candidate: Candidate) -> dict:
    if hasattr(candidate, "model_dump"):
        return candidate.model_dump()
    return candidate.dict()


def _clean(value) -> str:
    if value is None:
        return ""
    return EMAIL_PATTERN.sub("", str(value)).strip()


def _email(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _email_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _format_possible_emails(value) -> str:
    if not value:
        return "none"
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip()) or "none"
    return str(value).strip() or "none"


def _default_filters() -> list[str]:
    return [
        "seen candidates or papers unless --include-seen",
        "duplicate people",
        "max candidates per institution",
    ]
