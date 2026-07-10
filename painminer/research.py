"""Small, explicit helpers for describing a research request."""

from __future__ import annotations

import re
from typing import Any


ROLE_PATTERNS = {
    "founder": ("founder", "startup", "saas", "创业", "创始人"),
    "developer": ("developer", "programmer", "coding", "开发", "程序员"),
    "marketer": ("marketing", "growth", "营销", "增长"),
    "product_manager": ("product manager", "roadmap", "产品经理"),
    "consumer": ("parent", "fitness", "travel", "用户", "个人"),
}

# These are research-routing cues, not a claim that every matching post represents
# the target audience.  They keep a Chinese SaaS target on its bilingual route
# instead of letting a broad "developer" or "career" keyword dominate the sample.
SAAS_CUES = (
    "saas", "micro saas", "micro-saas", "indie hacker", "indiehackers",
    "bootstrap", "bootstrapped", "mrr", "arr", "churn", "subscription",
    "paying customer", "solo founder", "独立开发", "独立saa", "独立 saas",
    "订阅", "续费", "付费用户", "获客",
)


def relevance_lexicon(raw: str | None) -> list[str]:
    """Return conservative, inspectable routing terms for a target description."""
    text = str(raw or "").lower()
    terms: list[str] = []
    if any(cue in text for cue in SAAS_CUES):
        terms.extend(SAAS_CUES)
    for role, patterns in ROLE_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            terms.extend(patterns)
    terms.extend(re.findall(r"[a-z][a-z0-9_-]{3,}|[\u4e00-\u9fff]{2,}", text))
    return list(dict.fromkeys(terms))[:32]


def classify_target_relevance(post: dict[str, Any], target: str | None) -> dict[str, Any]:
    """Classify textual target fit without treating unrelated posts as evidence."""
    lexicon = relevance_lexicon(target)
    text = " ".join(
        str(post.get(key) or "")
        for key in ("title", "selftext", "story_text", "community", "subreddit")
    ).lower()
    matched = [term for term in lexicon if term and term in text]
    # ponytail: substring matching is intentionally transparent and dependency-free;
    # replace with an evaluated semantic classifier only after a labelled corpus exists.
    if matched:
        level = "high"
    elif lexicon:
        level = "low"
    else:
        level = "unknown"
    return {
        "target_relevance": level,
        "target_relevance_matched_terms": matched[:8],
        "target_relevance_method": "rule",
        "target_relevance_version": "target-fit-v1",
    }


def parse_target(raw: str | None) -> dict[str, Any]:
    """Describe only observable target cues; unspecified fields remain unknown."""
    text = str(raw or "").strip()
    lower = text.lower()
    roles = [role for role, patterns in ROLE_PATTERNS.items() if any(pattern in lower for pattern in patterns)]
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", text))
    has_saas_cue = any(cue in lower for cue in SAAS_CUES)
    languages = ["zh", "en"] if is_chinese and has_saas_cue else (["zh"] if is_chinese else ["en"])
    jobs = []
    for label, patterns in {
        "validate_idea": ("validate", "验证", "idea"),
        "acquire_customers": ("customer", "growth", "获客", "客户"),
        "reduce_workflow_friction": ("workflow", "manual", "效率", "流程"),
    }.items():
        if any(pattern in lower for pattern in patterns):
            jobs.append(label)
    return {
        "raw": text,
        "roles": roles or ["unknown"],
        "jobs": jobs or ["unknown"],
        "languages": languages,
        "relevance_lexicon": relevance_lexicon(text),
        "classification_method": "rule",
        "classification_version": "target-v1",
    }
