from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Job:
    """A job posting normalised from any source."""

    source: str  # e.g. "smartrecruiters:BoschGroup"
    external_id: str
    company: str
    title: str
    location: str
    url: str
    posted_at: Optional[str] = None  # ISO date, YYYY-MM-DD
    description: str = ""
    contract: str = ""  # e.g. "Estágio profissional", "Full-time"
    experience: str = ""  # e.g. "Entry Level", "Internship"
    work_model: str = ""  # on-site / hybrid / remote
    logo: str = ""  # image URL; from the source, or the `logo` of the config entry

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.external_id}"

    def full_text(self) -> str:
        return " ".join(
            [self.title, self.experience, self.contract, self.work_model, self.description]
        )
