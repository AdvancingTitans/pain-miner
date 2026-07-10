"""Small, dependency-free models shared by structured Pain Miner outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class CommunityProfile:
    platform: str
    community: str
    title: str | None
    description: str | None
    members: int | None
    audience_roles: list[str]
    common_post_types: list[str]
    discussion_style: list[str]
    rules_summary: dict[str, str]
    commercial_content_policy: str
    research_strengths: list[str]
    bias_risks: list[str]
    activity_metrics: dict[str, Any]
    profile_fetched_at: str
    source_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
