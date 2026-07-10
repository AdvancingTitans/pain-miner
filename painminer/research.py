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


def parse_target(raw: str | None) -> dict[str, Any]:
    """Describe only observable target cues; unspecified fields remain unknown."""
    text = str(raw or "").strip()
    lower = text.lower()
    roles = [role for role, patterns in ROLE_PATTERNS.items() if any(pattern in lower for pattern in patterns)]
    language = "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"
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
        "languages": [language],
        "classification_method": "rule",
        "classification_version": "target-v1",
    }
