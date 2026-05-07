from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Paper(BaseModel):
    source: str = ""
    title: str = ""
    abstract: str = ""
    url: str = ""
    published_date: str = ""
    authors: list[str] = Field(default_factory=list)
    cited_by_count: int = 0
    unique_key: str = ""

    def model_post_init(self, __context) -> None:
        if not self.unique_key:
            self.unique_key = _make_key(self.url, self.title)


def _make_key(url: str, title: str) -> str:
    import hashlib
    base = url.strip() if url.strip() else title.strip().lower()
    return hashlib.sha256(base.encode()).hexdigest()[:16]


class PaperScore(BaseModel):
    relevance: float = 5.0
    novelty: float = 5.0
    grant_potential: float = 5.0
    collaboration_potential: float = 5.0
    industry_potential: float = 5.0
    teaching_public_value: float = 5.0
    feasibility: float = 5.0
    risk: float = 5.0
    agent_commentary: str = ""
    evidence_gaps: list[str] = Field(default_factory=list)
    recommended_action: str = "save_for_later"


class ScoredPaper(BaseModel):
    paper: Paper
    score: PaperScore
    total_score: float = 0.0


class ResearchProfile(BaseModel):
    research_topics: list[str] = Field(default_factory=list)
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    watchlist: dict = Field(default_factory=dict)
    negative_filters: list[str] = Field(default_factory=list)
    protected_topics: list[str] = Field(default_factory=list)
