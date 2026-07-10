"""Deterministic, evidence-preserving post analysis for Pain Miner.

No aggregate opportunity score is calculated here.  The output intentionally keeps
the counts and evidence links that support every qualitative signal.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlsplit

from painminer.research import classify_target_relevance, parse_target


DIRECT_INTENTS = {
    "complaint", "help_request", "alternative_search", "recommendation_request",
    "workaround_share", "switching_story", "purchase_intent",
}

TASK_BY_INTENT = {
    "alternative_search": "replace an unsatisfactory existing solution",
    "recommendation_request": "choose a suitable solution",
    "purchase_intent": "evaluate whether a paid solution is worthwhile",
    "switching_story": "migrate away from a current solution",
    "workaround_share": "complete the task despite a missing workflow",
    "help_request": "unblock a task",
    "complaint": "complete a task with less friction",
}


def _text(post: dict[str, Any]) -> str:
    return " ".join(str(post.get(key) or "") for key in ("title", "selftext", "story_text"))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", text.lower()))


def _stable_url(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}".lower()


def _append_flag(post: dict[str, Any], flag: str) -> None:
    flags = post.setdefault("risk_flags", [])
    if flag not in flags:
        flags.append(flag)


def _observed_risks(post: dict[str, Any]) -> None:
    text = f"{_text(post)} {post.get('url') or ''}"
    if re.search(r"\b(?:affiliate|referral|ref=|utm_[a-z_]+|promo code)\b", text, re.IGNORECASE):
        _append_flag(post, "post_contains_affiliate_pattern")
    if re.search(r"\b(?:breaking|announced|launch(?:ed|ing)?|news)\b|突发|发布会|新闻", _text(post), re.IGNORECASE):
        _append_flag(post, "event_driven")


def _similarity(first: dict[str, Any], second: dict[str, Any]) -> float:
    a, b = _tokens(_text(first)), _tokens(_text(second))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def deduplicate_posts(posts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """Mark exact and near-duplicate public text without discarding audit evidence."""
    annotated = [deepcopy(post) for post in posts]
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, str]] = []
    by_key: dict[str, dict[str, Any]] = {}

    # ponytail: O(n²) near-duplicate comparison is deliberate for small research runs;
    # replace with a locality-sensitive index if a run regularly exceeds thousands of posts.
    for post in annotated:
        _observed_risks(post)
        key = _stable_url(str(post.get("url") or "")) or f"{post.get('platform')}:{post.get('id')}"
        canonical = by_key.get(key)
        if canonical is None:
            canonical = next((item for item in unique if _similarity(item, post) >= 0.92), None)
        if canonical is not None:
            _append_flag(post, "duplicate_content")
            post["duplicate_of"] = canonical.get("id") or canonical.get("url") or "unknown"
            duplicates.append({
                "post_id": str(post.get("id") or post.get("url") or "unknown"),
                "canonical_id": str(post["duplicate_of"]),
            })
            continue
        by_key[key] = post
        unique.append(post)
    return annotated, unique, duplicates


def attach_author_context(posts: list[dict[str, Any]]) -> None:
    """Attach weak, run-local author context without retrieving profile history."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        author = str(post.get("author") or post.get("member") or "")
        if author and author not in {"[deleted]", "unknown"}:
            grouped[(str(post.get("community") or "unknown"), author)].append(post)
    for post in posts:
        author = str(post.get("author") or post.get("member") or "")
        sample = grouped.get((str(post.get("community") or "unknown"), author), [])
        promotions = sum(item.get("post_intent") == "promotion" for item in sample)
        post["author_context"] = {
            "account_age_days": None,
            "total_karma": None,
            "community_post_count_sample": len(sample) if sample else None,
            "recent_promotion_ratio": round(promotions / len(sample), 2) if sample else None,
            "possible_vendor": None,
            "confidence": "low" if sample else "unknown",
            "source": "current_public_sample_only",
        }


def _level(value: int, *, medium: int = 2, high: int = 5, unknown: bool = False) -> str:
    if unknown:
        return "unknown"
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"


def _recency(posts: list[dict[str, Any]]) -> str:
    timestamps = []
    for post in posts:
        raw = post.get("posted")
        if not raw:
            continue
        try:
            timestamps.append(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
        except ValueError:
            continue
    if not timestamps:
        return "unknown"
    age_days = (datetime.now(timezone.utc) - max(timestamps)).total_seconds() / 86400
    return "high" if age_days <= 7 else ("medium" if age_days <= 90 else "low")


def _evidence_ref(post: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": post.get("id"), "community": post.get("community"), "url": post.get("url"),
        "title": post.get("title"), "intent": post.get("post_intent"),
        "evidence_type": post.get("evidence_type"), "risk_flags": post.get("risk_flags", []),
        "current_solution": post.get("commercial_signals", {}).get("current_solution"),
    }


def _cluster_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        themes = post.get("pain_themes") or ["general"]
        for theme in themes:
            groups[str(theme)].append(post)

    clusters = []
    for theme, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        intent_counts = Counter(str(post.get("post_intent") or "unknown") for post in members)
        primary_count = sum(post.get("evidence_type") == "primary_evidence" for post in members)
        counter_count = sum(post.get("evidence_type") == "counter_evidence" for post in members)
        risk_count = sum(bool(post.get("risk_flags")) for post in members)
        comment_support = [
            {"post_id": post.get("id"), "community": post.get("community"), "url": post.get("url"), "text": item.get("text")}
            for post in members for item in post.get("comment_evidence", [])
            if item.get("evidence_type") == "supporting_evidence"
        ]
        communities = {str(post.get("community") or "unknown") for post in members}
        workaround_count = sum(bool(post.get("commercial_signals", {}).get("workaround_present")) for post in members)
        explicit_purchase = sum(post.get("commercial_signals", {}).get("willingness_to_pay") == "explicit" for post in members)
        implicit_purchase = sum(post.get("commercial_signals", {}).get("willingness_to_pay") == "implicit" for post in members)
        dissatisfaction = sum(
            post.get("post_intent") in {"alternative_search", "switching_story", "complaint"}
            for post in members
        )
        representative = members[0]
        dominant_intent = intent_counts.most_common(1)[0][0]
        task = TASK_BY_INTENT.get(dominant_intent, "understand the user task")
        signal_basis = {
            "unique_posts": len(members), "communities": len(communities),
            "primary_evidence": primary_count, "counter_evidence": counter_count,
            "risk_flagged_posts": risk_count, "workarounds": workaround_count,
            "supporting_comment_evidence": len(comment_support),
            "explicit_purchase_signals": explicit_purchase, "implicit_purchase_signals": implicit_purchase,
            "existing_solution_dissatisfaction": dissatisfaction,
        }
        quality = "high" if primary_count == len(members) and not risk_count else (
            "medium" if primary_count else "low"
        )
        clusters.append({
            "pain_id": f"pain_{len(clusters) + 1:03d}",
            "label": theme,
            "pain_structure": {
                "domain": theme,
                "task_scenario": task,
                "specific_obstacle": str(representative.get("title") or "unknown"),
            },
            "signals": {
                "frequency": _level(len(members)),
                "cross_community": _level(len(communities), medium=2, high=2),
                "recency": _recency(members),
                "workaround_cost": _level(workaround_count, medium=1, high=3),
                "purchase_intent": "high" if explicit_purchase else ("medium" if implicit_purchase else "low"),
                "existing_solution_dissatisfaction": _level(dissatisfaction, medium=1, high=3),
                "evidence_quality": quality,
                "basis": signal_basis,
            },
            "supporting_evidence": [_evidence_ref(post) for post in members if post.get("evidence_type") == "primary_evidence"],
            "supporting_comment_evidence": comment_support,
            "counter_evidence": [_evidence_ref(post) for post in members if post.get("evidence_type") == "counter_evidence"],
            "commercially_contaminated": [_evidence_ref(post) for post in members if post.get("evidence_type") == "commercially_contaminated"],
            "existing_alternatives": list(dict.fromkeys(
                signal.get("current_solution") for signal in (post.get("commercial_signals", {}) for post in members)
                if signal.get("current_solution")
            )),
            "source_posts": [_evidence_ref(post) for post in members],
        })
    return clusters


def _community_comparisons(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons = []
    for cluster in clusters:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for evidence in cluster["source_posts"]:
            grouped[str(evidence.get("community") or "unknown")].append(evidence)
        if len(grouped) < 2:
            continue
        differences = []
        for community, evidence in sorted(grouped.items()):
            differences.append({
                "community": community,
                "post_count": len(evidence),
                "dominant_intents": [name for name, _ in Counter(item.get("intent") for item in evidence).most_common(3)],
                "common_current_solutions": list(dict.fromkeys(
                    item.get("current_solution") for item in evidence if item.get("current_solution")
                )),
                "sample_urls": [item.get("url") for item in evidence if item.get("url")][:3],
            })
        comparisons.append({
            "pain_id": cluster["pain_id"], "topic": cluster["label"],
            "shared_pain": cluster["label"], "community_differences": differences,
            "possible_root_problem": "unknown — requires human review of the cited evidence and counter-evidence.",
        })
    return comparisons


def _opportunity_cards(clusters: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    cards = []
    for cluster in clusters:
        structure = cluster["pain_structure"]
        cards.append({
            "opportunity": f"Help {target or 'the target user'} address {cluster['label']}",
            "target_user": target or "unknown",
            "job_to_be_done": structure["task_scenario"],
            "supporting_evidence": cluster["supporting_evidence"],
            "counter_evidence": cluster["counter_evidence"],
            "existing_alternatives": cluster["existing_alternatives"],
            "unresolved_questions": [
                "Which outcome would make users change their current workflow?",
                "Which part of the task is worth paying for rather than handling manually?",
            ],
            "recommended_validation": {
                "method": "concierge_test",
                "action": f"Manually help 5 {target or 'target'} users with: {structure['specific_obstacle']}",
                "success_signal": "At least 3 users ask to repeat the workflow or state a willingness to pay.",
                "abandon_signal": "Most users prefer their existing workaround or do not return after the assisted result.",
            },
            "source_pain_id": cluster["pain_id"],
        })
    return cards


def analyze_research(payload: dict[str, Any]) -> dict[str, Any]:
    """Produce P0/P1 research artifacts from a run or single-source JSON output."""
    step_b = payload.get("step_b") if isinstance(payload.get("step_b"), dict) else {}
    source_posts = step_b.get("posts") if isinstance(step_b.get("posts"), list) else payload.get("posts", [])
    target = str(payload.get("target") or "")
    annotated, _unique_posts, duplicates = deduplicate_posts(source_posts if isinstance(source_posts, list) else [])
    for post in annotated:
        if not post.get("target_relevance"):
            post.update(classify_target_relevance(post, target))
    attach_author_context(annotated)
    # Reuse the annotated canonical copies so author context and risk flags stay consistent.
    unique_annotated = [post for post in annotated if "duplicate_of" not in post]
    research_posts = [post for post in unique_annotated if post.get("target_relevance") != "low"]
    primary_posts = [post for post in research_posts if post.get("evidence_type") == "primary_evidence"]
    quality_gate = payload.get("quality_gate") if isinstance(payload.get("quality_gate"), dict) else {}
    min_primary = int(quality_gate.get("min_primary_evidence", 5))
    verdict = "READY" if len(primary_posts) >= min_primary else "INSUFFICIENT_EVIDENCE"
    clusters = _cluster_posts(research_posts)
    comparisons = _community_comparisons(clusters)
    next_actions = (
        [] if verdict == "READY" else [
            "Widen the time window or lower thresholds only with the resulting scope recorded.",
            "Use a healthy source profile (for example HN-first when Reddit is blocked).",
            "Review the target/community plan before treating low-relevance posts as evidence.",
        ]
    )
    return {
        "schema_version": "2.3",
        "target": payload.get("target"),
        "target_profile": parse_target(target),
        "deduplication": {
            "input_count": len(annotated), "unique_count": len(unique_annotated),
            "duplicate_count": len(duplicates), "duplicates": duplicates,
        },
        "posts": annotated,
        "relevance_filter": {
            "included_count": len(research_posts),
            "excluded_low_relevance_count": len(unique_annotated) - len(research_posts),
            "policy": "Low-relevance posts remain auditable but cannot support clusters or opportunities.",
        },
        "evidence_verdict": {
            "status": verdict,
            "primary_evidence_count": len(primary_posts),
            "minimum_primary_evidence": min_primary,
            "next_actions": next_actions,
        },
        "pain_clusters": clusters,
        "community_comparisons": comparisons,
        "community_comparisons_status": "available" if comparisons else "not_applicable_or_insufficient_cross_community_evidence",
        "opportunities": _opportunity_cards(clusters, target) if verdict == "READY" else [],
        "limitations": [
            "Signals are rule- and sample-based; they are not an aggregate opportunity score.",
            "Author context is limited to the current public sample; account age, karma, and private history are unknown.",
            "Product alternatives only include solutions explicitly observed in source posts.",
            *( ["Insufficient primary, target-relevant evidence: opportunities are intentionally suppressed."] if verdict != "READY" else [] ),
        ],
    }
