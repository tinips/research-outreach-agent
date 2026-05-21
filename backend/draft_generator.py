import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from .models import Candidate, DraftCandidate


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_TEMPLATE_PATH = PROMPTS_DIR / "email_template.md"
COMPUTE_SENTENCE = "I also have access to local compute and can help run experiments asynchronously if needed."
DEFAULT_CLOSING_QUESTION = (
    "Would you be open to considering whether I could contribute remotely to one of your ongoing projects?"
)
RESEARCH_STAFF_CLOSING_QUESTION = (
    "Would it be useful if I helped remotely with research or engineering work around this line of work?"
)
FORBIDDEN_PHRASES = [
    "I can work for free",
    "I do not need to be paid",
    "unpaid internship",
    "mass email",
    "I am desperate for experience",
]
COMPUTE_RELATED_TERMS = [
    "experiment",
    "benchmark",
    "training",
    "simulation",
    "evaluation",
    "evaluate",
    "reproducibility",
    "reproducible",
]
ROLE_PROFESSOR_TERMS = ["professor", "prof."]
RESEARCH_STAFF_TERMS = ["phd", "doctoral", "postdoc", "postdoctoral", "research scientist", "scientist"]
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "toward",
    "towards",
    "with",
}

SENDER_DEFAULTS = {
    "sender_name": "Example Sender",
    "sender_background": "a researcher/engineer working on reproducible AI systems",
    "sender_github": "https://github.com/your-username",
    "sender_linkedin": "https://www.linkedin.com/in/your-profile",
    "cv_link": "attached CV",
}


def load_candidates_from_json(path: Path | str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        return []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def generate_drafts_from_candidates_json(
    path: Path | str,
    *,
    template_path: Path | str = DEFAULT_TEMPLATE_PATH,
    limit: int | None = None,
) -> list[DraftCandidate]:
    return generate_drafts(load_candidates_from_json(path), template_path=template_path, limit=limit)


def generate_drafts(
    candidates: Iterable[Candidate | dict[str, Any]],
    *,
    template_path: Path | str = DEFAULT_TEMPLATE_PATH,
    limit: int | None = None,
) -> list[DraftCandidate]:
    template = Path(template_path).read_text(encoding="utf-8")
    draft_candidates = list(candidates)
    if limit is not None:
        draft_candidates = draft_candidates[: max(0, limit)]
    return [_generate_draft(_candidate_to_dict(candidate), template) for candidate in draft_candidates]


def _generate_draft(candidate: dict[str, Any], template: str) -> DraftCandidate:
    name = _clean(candidate.get("name"))
    role = _clean(candidate.get("role") or candidate.get("inferred_role"))
    paper_title = _clean(candidate.get("paper_title"))
    topic_or_area = _topic_or_area(candidate, paper_title)
    optional_compute_sentence = COMPUTE_SENTENCE if _should_include_compute_sentence(candidate) else ""
    closing_question = (
        RESEARCH_STAFF_CLOSING_QUESTION if _is_research_staff_role(role) else DEFAULT_CLOSING_QUESTION
    )
    rendered = _render_template(
        template,
        {
            **_sender_template_values(),
            "topic_or_area": topic_or_area,
            "recipient_name": _recipient_name(name, role),
            "paper_title": paper_title or "[paper title missing]",
            "specific_interest": _specific_interest(candidate, topic_or_area),
            "contribution_angle": _contribution_angle(candidate),
            "optional_compute_sentence": optional_compute_sentence,
            "closing_question": closing_question,
        },
    )
    subject, body = _split_subject_and_body(rendered)
    verification_notes = _verification_notes(subject=subject, body=body, paper_title=paper_title)

    return DraftCandidate(
        candidate_key=_clean(candidate.get("candidate_key")),
        person_key=_clean(candidate.get("person_key")) or None,
        paper_key=_clean(candidate.get("paper_key")) or None,
        candidate_name=name,
        group=_clean(candidate.get("group")),
        email=_clean(candidate.get("email")) or None,
        email_confidence=_clean(candidate.get("email_confidence")),
        name=name,
        institution=_clean(candidate.get("institution")) or None,
        paper_title=paper_title or None,
        paper_url=_clean(candidate.get("paper_url")) or None,
        subject=subject,
        body=body,
        draft_body=body,
        verification_notes=verification_notes,
    )


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered_lines = []
    for line in template.splitlines():
        if line.strip() == "{optional_compute_sentence}" and not values["optional_compute_sentence"]:
            continue
        rendered_lines.append(line.format(**values))
    rendered = "\n".join(rendered_lines).strip()
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered


def _split_subject_and_body(rendered: str) -> tuple[str, str]:
    lines = rendered.splitlines()
    if lines and lines[0].startswith("Subject: "):
        subject = lines[0].replace("Subject: ", "", 1).strip()
        body = "\n".join(lines[1:]).strip()
        return subject, body
    return "", rendered.strip()


def _recipient_name(name: str, role: str) -> str:
    if not name:
        return "Researcher"
    if _is_professor_role(role):
        last_name = _last_name(name)
        if last_name:
            return f"Professor {last_name}"
    first_name = _first_name(name)
    return first_name or name


def _topic_or_area(candidate: dict[str, Any], paper_title: str) -> str:
    for key in ("topic", "search_topic", "topic_or_area", "area"):
        value = _clean(candidate.get(key))
        if value:
            return _short_phrase(value)
    if paper_title:
        return _short_phrase_from_paper_title(paper_title)
    return "AI research"


def _short_phrase(value: str) -> str:
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"[\[\]{}()\"']", "", value)
    value = value.replace(":", " ")
    value = re.sub(r"\s+", " ", value).strip(" ,;.-")
    if not value:
        return "AI research"
    words = value.split()
    if len(words) <= 7:
        return value
    selected = [word for word in words if word.lower().strip(".,;:-") not in STOPWORDS]
    phrase_words = selected[:7] if len(selected) >= 3 else words[:7]
    return " ".join(phrase_words).strip(" ,;.-") or "AI research"


def _short_phrase_from_paper_title(paper_title: str) -> str:
    cleaned = _short_phrase(paper_title)
    if cleaned.casefold() != paper_title.casefold():
        return cleaned
    words = cleaned.split()
    if len(words) <= 1:
        return "AI research"
    selected = [word for word in words if word.lower().strip(".,;:-") not in STOPWORDS]
    phrase_words = selected[: max(1, min(5, len(selected) - 1))] if len(selected) > 1 else words[:-1]
    phrase = " ".join(phrase_words).strip(" ,;.-")
    if phrase and phrase.casefold() != paper_title.casefold():
        return phrase
    return "AI research"


def _should_include_compute_sentence(candidate: dict[str, Any]) -> bool:
    text = " ".join(
        _clean(candidate.get(key))
        for key in (
            "topic",
            "search_topic",
            "topic_or_area",
            "area",
            "opportunity_angle",
            "suggested_outreach_angle",
        )
    ).lower()
    return any(term in text for term in COMPUTE_RELATED_TERMS)


def _verification_notes(*, subject: str, body: str, paper_title: str) -> str:
    failures = []
    if paper_title and paper_title.casefold() in subject.casefold():
        failures.append("subject contains paper title")
    if not body.startswith("Dear"):
        failures.append("body does not start with Dear")
    if not paper_title or f'"{paper_title}"' not in body:
        failures.append("body does not include exact paper title in quotes")
    for phrase in FORBIDDEN_PHRASES:
        if phrase.casefold() in body.casefold():
            failures.append(f"body includes forbidden phrase: {phrase}")
    if failures:
        return "needs_review: " + "; ".join(failures)
    return "passed deterministic template checks"


def _is_professor_role(role: str) -> bool:
    role_lower = role.lower()
    return any(term in role_lower for term in ROLE_PROFESSOR_TERMS)


def _is_research_staff_role(role: str) -> bool:
    role_lower = role.lower()
    return any(term in role_lower for term in RESEARCH_STAFF_TERMS)


def _first_name(name: str) -> str:
    parts = name.split()
    return parts[0].strip(" ,") if parts else ""


def _last_name(name: str) -> str:
    parts = [part.strip(" ,") for part in name.split() if part.strip(" ,")]
    return parts[-1] if parts else ""


def _candidate_to_dict(candidate: Candidate | dict[str, Any]) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate
    if hasattr(candidate, "model_dump"):
        return candidate.model_dump()
    return candidate.dict()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _sender_template_values() -> dict[str, str]:
    _load_dotenv_if_available()
    return {
        key: _clean(os.getenv(key.upper())) or default
        for key, default in SENDER_DEFAULTS.items()
    }


def _load_dotenv_if_available() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=False)


def _specific_interest(candidate: dict[str, Any], topic_or_area: str) -> str:
    for key in ("specific_interest", "suggested_outreach_angle", "opportunity_angle"):
        value = _clean(candidate.get(key))
        if value:
            return value
    return f"the broader direction of this work around {topic_or_area}"


def _contribution_angle(candidate: dict[str, Any]) -> str:
    for key in ("contribution_angle", "suggested_outreach_angle", "opportunity_angle"):
        value = _clean(candidate.get(key))
        if value:
            return value
    return "implementation, experiments, evaluation, reproducibility, or research tooling"
