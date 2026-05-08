from datetime import date
from math import log10
from typing import Any, Optional


TARGET_LAB_TERMS = (
    "stanford",
    "mit",
    "massachusetts institute of technology",
    "berkeley",
    "uc berkeley",
    "carnegie mellon",
    "cmu",
    "epfl",
    "eth zurich",
    "oxford",
    "cambridge",
    "ucl",
    "university college london",
    "mila",
    "toronto",
    "princeton",
    "university of washington",
    "nyu",
    "new york university",
    "inria",
    "max planck",
    "ellis",
    "alan turing institute",
    "google deepmind",
    "deepmind",
    "openai",
    "anthropic",
    "meta ai",
    "microsoft research",
    "ai research lab",
)

BROAD_AI_TERMS = (
    "artificial intelligence",
    "large language model",
    "llm",
    "agent",
    "agentic",
    "retrieval augmented generation",
    "rag",
    "evaluation",
    "multimodal",
    "computer vision",
    "robotics",
    "embodied",
    "reinforcement learning",
    "generative",
    "diffusion",
    "ai for science",
    "data-centric",
    "infrastructure",
    "interpretability",
    "safety",
    "automated reasoning",
    "scientific machine learning",
    "human-ai",
    "applied machine learning",
    "benchmark",
    "dataset",
)

RESEARCH_ENGINEERING_TERMS = (
    "implementation",
    "experiment",
    "evaluation",
    "benchmark",
    "reproducibility",
    "dataset",
    "pipeline",
    "tooling",
    "system",
    "infrastructure",
    "simulation",
    "training",
)

PROFILE_TERMS = (
    "pytorch",
    "trajectory",
    "constraint",
    "geometric",
    "robot",
    "demonstration",
    "synthetic data",
    "data pipeline",
    "evaluation",
    "reproducible",
)


def score_candidate(
    *,
    topic: str,
    work: dict[str, Any],
    author_url: Optional[str],
    institution: Optional[str],
    paper_url: Optional[str],
) -> dict[str, float | str]:
    text = _combined_text(topic, work, institution)
    lab_signal_score = _lab_signal_score(institution)
    paper_signal_score = _paper_signal_score(
        work.get("publication_year"),
        work.get("cited_by_count"),
    )
    project_activity_score = _project_activity_score(work, paper_url)
    contactability_score = _contactability_score(author_url, institution)
    contribution_angle_score = _keyword_overlap_score(
        text,
        BROAD_AI_TERMS + RESEARCH_ENGINEERING_TERMS,
    )
    profile_fit_score = _keyword_overlap_score(text, PROFILE_TERMS)

    search_signal_score = round(
        (0.30 * lab_signal_score)
        + (0.25 * paper_signal_score)
        + (0.20 * project_activity_score)
        + (0.10 * contactability_score)
        + (0.10 * contribution_angle_score)
        + (0.05 * profile_fit_score),
        3,
    )

    return {
        "lab_signal_score": lab_signal_score,
        "paper_signal_score": paper_signal_score,
        "project_activity_score": project_activity_score,
        "contactability_score": contactability_score,
        "contribution_angle_score": contribution_angle_score,
        "profile_fit_score": profile_fit_score,
        "search_signal_score": search_signal_score,
        "fit_score": search_signal_score,
        "contact_priority": _contact_priority(search_signal_score),
        "suggested_outreach_angle": _suggested_outreach_angle(text),
    }


def _combined_text(
    topic: str,
    work: dict[str, Any],
    institution: Optional[str],
) -> str:
    parts = [
        topic,
        work.get("display_name"),
        work.get("title"),
        work.get("abstract"),
        institution,
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _lab_signal_score(institution: Optional[str]) -> float:
    if not institution:
        return 0.0

    normalized = institution.lower()
    if any(term in normalized for term in TARGET_LAB_TERMS):
        return 1.0
    if any(term in normalized for term in ("university", "institute", "laboratory", "lab")):
        return 0.55
    return 0.25


def _paper_signal_score(
    publication_year: Optional[int],
    cited_by_count: Optional[int],
) -> float:
    current_year = date.today().year
    if isinstance(publication_year, int):
        age = max(0, current_year - publication_year)
        recency_score = max(0.0, 1.0 - (age / 8))
    else:
        recency_score = 0.25

    citation_count = cited_by_count if isinstance(cited_by_count, int) else 0
    citation_score = min(log10(citation_count + 1) / 4, 1.0)

    return round((0.55 * recency_score) + (0.45 * citation_score), 3)


def _project_activity_score(
    work: dict[str, Any],
    paper_url: Optional[str],
) -> float:
    score = 0.0
    if work.get("doi"):
        score += 0.35
    if paper_url:
        score += 0.25

    primary_location = work.get("primary_location") or {}
    if isinstance(primary_location, dict):
        if primary_location.get("landing_page_url"):
            score += 0.2
        if primary_location.get("pdf_url"):
            score += 0.1

    open_access = work.get("open_access") or {}
    if isinstance(open_access, dict) and open_access.get("oa_url"):
        score += 0.1

    # Later versions can add explicit GitHub, project page, dataset, and demo detection.
    return round(min(score, 1.0), 3)


def _contactability_score(
    author_url: Optional[str],
    institution: Optional[str],
) -> float:
    score = 0.0
    if author_url:
        score += 0.55
    if institution:
        score += 0.45
    return round(score, 3)


def _keyword_overlap_score(text: str, terms: tuple[str, ...]) -> float:
    if not text:
        return 0.0

    matches = sum(1 for term in terms if term in text)
    return round(min(matches / 4, 1.0), 3)


def _contact_priority(search_signal_score: float) -> str:
    if search_signal_score >= 0.70:
        return "high"
    if search_signal_score >= 0.45:
        return "medium"
    return "low"


def _suggested_outreach_angle(text: str) -> str:
    if "benchmark" in text or "evaluation" in text:
        return (
            "Offer research engineering help with benchmarks, evaluation runs, "
            "reproducibility checks, and analysis tooling."
        )
    if "robot" in text or "embodied" in text or "simulation" in text:
        return (
            "Offer help with experimental pipelines, simulation workflows, "
            "trajectory analysis, and reproducible robotics evaluation."
        )
    if "dataset" in text or "data" in text:
        return (
            "Offer help with data pipelines, dataset preparation, experiment "
            "tracking, and reproducible research tooling."
        )
    return (
        "Offer a small remote research engineering collaboration focused on "
        "implementation, experiments, evaluation, reproducibility, or tooling."
    )
