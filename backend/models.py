from typing import Literal, Optional

from pydantic import BaseModel, Field


class SearchResearchersRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Research topic to search for.")
    limit: int = Field(default=5, ge=1, description="Maximum number of candidates to return.")
    save_csv: bool = Field(default=False, description="Whether to save candidates to outputs/candidates.csv.")
    max_authors_per_paper: int = Field(default=1, ge=1)
    from_year: int = Field(default=2023, ge=1900)
    sort_by: Literal["relevance", "citations", "recent"] = "relevance"


class Candidate(BaseModel):
    source: str = "openalex"
    paper_id: Optional[str] = None
    person_key: Optional[str] = None
    paper_key: Optional[str] = None
    candidate_key: Optional[str] = None
    status: str = "new"
    group: Literal["stretch", "realistic", "balanced", "balanced-fill"] = "balanced"
    inferred_role: str = "unknown"
    name: str
    institution: Optional[str] = None
    author_url: Optional[str] = None
    email: Optional[str] = None
    email_source: Optional[str] = None
    email_confidence: str = ""
    email_evidence: str = ""
    possible_emails: list[str] = Field(default_factory=list)
    email_verification_notes: str = ""
    paper_title: Optional[str] = None
    paper_year: Optional[int] = None
    paper_url: Optional[str] = None
    abstract: Optional[str] = None
    cited_by_count: Optional[int] = None
    opportunity_angle: str
    research_signal_score: float = 0.0
    outreach_probability_score: float = 0.0
    contribution_fit_score: float = 0.0
    lab_signal_score: float
    paper_signal_score: float
    project_activity_score: float
    contactability_score: float
    contribution_angle_score: float
    profile_fit_score: float
    novelty_score: float = 1.0
    search_signal_score: float
    fit_score: float
    final_score: float = 0.0
    contact_priority: Literal["high", "medium", "low"]
    selection_reason: str = ""
    suggested_outreach_angle: str
    seen_status: Literal["new", "seen_before", "recently_shortlisted", "fallback_recently_seen"] = "new"
    verification_notes: str = ""


class SearchResearchersResponse(BaseModel):
    topic: str
    limit: int
    count: int
    candidates: list[Candidate]
    csv_path: Optional[str] = None


class DraftCandidate(BaseModel):
    candidate_key: str
    person_key: Optional[str] = None
    paper_key: Optional[str] = None
    candidate_name: Optional[str] = None
    group: str = ""
    email: Optional[str] = None
    email_confidence: str = ""
    name: str
    institution: Optional[str] = None
    paper_title: Optional[str] = None
    paper_url: Optional[str] = None
    subject: str
    body: Optional[str] = None
    draft_body: str
    verification_notes: str = ""
