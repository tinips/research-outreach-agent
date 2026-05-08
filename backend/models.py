from typing import Literal, Optional

from pydantic import BaseModel, Field


class SearchResearchersRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Research topic to search for.")
    limit: int = Field(
        default=5,
        ge=1,
        description="Maximum number of candidates to return. Values above 50 are capped.",
    )
    save_csv: bool = Field(
        default=False,
        description="Whether to save returned candidates to outputs/candidates.csv.",
    )
    max_authors_per_paper: int = Field(
        default=1,
        ge=1,
        description="Maximum number of candidate authors to return from each paper.",
    )
    from_year: int = Field(
        default=2023,
        ge=1900,
        description="Only search papers published from this year onward.",
    )
    sort_by: Literal["relevance", "citations", "recent"] = Field(
        default="relevance",
        description="OpenAlex sorting strategy.",
    )


class Candidate(BaseModel):
    source: str = "openalex"
    paper_id: Optional[str] = None
    person_key: Optional[str] = None
    paper_key: Optional[str] = None
    candidate_key: Optional[str] = None
    status: str = "new"
    name: str
    institution: Optional[str] = None
    author_url: Optional[str] = None
    paper_title: Optional[str] = None
    paper_year: Optional[int] = None
    paper_url: Optional[str] = None
    abstract: Optional[str] = None
    cited_by_count: Optional[int] = None
    opportunity_angle: str
    lab_signal_score: float
    paper_signal_score: float
    project_activity_score: float
    contactability_score: float
    contribution_angle_score: float
    profile_fit_score: float
    search_signal_score: float
    fit_score: float
    contact_priority: Literal["high", "medium", "low"]
    suggested_outreach_angle: str


class SearchResearchersResponse(BaseModel):
    topic: str
    limit: int
    count: int
    candidates: list[Candidate]
    csv_path: Optional[str] = None
