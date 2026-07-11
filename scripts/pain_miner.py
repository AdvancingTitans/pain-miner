#!/usr/bin/env python3
"""Pain Miner — domain-agnostic community pain-point scanner.

Platforms (all login-free by default):
  - Reddit via Arctic Shift (primary)
  - Hacker News via Algolia + Firebase (supplement)
  - V2EX public API (Chinese supplement)
  - Browser via Jina Reader r.jina.ai (fallback, no login)
"""

from __future__ import annotations

import argparse
import os
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from painminer.analysis import analyze_research
from painminer.models import CommunityProfile
from painminer.report import render_report
from painminer.research import classify_target_relevance, parse_target

ARCTIC_POSTS = "https://arctic-shift.photon-reddit.com/api/posts/search"
ARCTIC_COMMENTS = "https://arctic-shift.photon-reddit.com/api/comments/search"
HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"
V2EX_HOT = "https://www.v2ex.com/api/topics/hot.json"
V2EX_NODE = "https://www.v2ex.com/api/topics/show.json"
JINA_READER = "https://r.jina.ai/{url}"

# Public endpoints are shared resources.  These defaults deliberately favour
# fewer requests over a marginally faster report; override only for a source
# owner's documented allowance.
HTTP_MAX_RETRIES = max(0, int(os.getenv("PAIN_MINER_HTTP_MAX_RETRIES", "1")))
SOURCE_MIN_INTERVAL_SECONDS = max(0.0, float(os.getenv("PAIN_MINER_SOURCE_MIN_INTERVAL", "1.2")))
HTTP_RETRYABLE_CODES = {408, 425, 500, 502, 503, 504}
HTTP_USER_AGENT = "pain-miner/2.3.1 (+https://github.com/AdvancingTitans/pain-miner)"
_SOURCE_LAST_REQUEST: dict[str, float] = {}
_SOURCE_CIRCUITS: dict[str, str] = {}
_REDDIT_POST_CACHE: dict[tuple[str, int], list[dict]] = {}
_REDDIT_COMMENT_CACHE: dict[tuple[str, int], list[dict]] = {}


class SourceCircuitOpen(RuntimeError):
    """A source has returned a terminal block/rate limit in this process."""

    def __init__(self, host: str, reason: str):
        self.host = host
        self.reason = reason
        super().__init__(f"{host} circuit open: {reason}")


def reset_runtime_state() -> None:
    """Clear per-process pacing, circuit-breaker, and listing caches (mainly tests)."""
    _SOURCE_LAST_REQUEST.clear()
    _SOURCE_CIRCUITS.clear()
    _REDDIT_POST_CACHE.clear()
    _REDDIT_COMMENT_CACHE.clear()

# Keyword → community hints (expandable; Agent may override via --subs/--hn-query/--v2ex-node)
COMMUNITY_HINTS: list[dict[str, Any]] = [
    {
        "keywords": ["saas", "micro saas", "indie hacker", "bootstrap", "独立开发", "独立 saas", "独立saas"],
        "reddit": ["SaaS", "indiehackers", "SideProject", "EntrepreneurRideAlong", "Entrepreneur", "startups"],
        "hn": ["indie hacker", "micro saas", "bootstrap saas", "solo founder first customers"],
        "v2ex": ["create", "share", "programmer"],
    },
    {
        "keywords": ["finance", "invest", "理财", "投资", "股票", "基金", "fire", "退休", "负债", "budget"],
        "reddit": ["personalfinance", "Bogleheads", "investing", "financialindependence", "algotrading"],
        "hn": ["personal finance investing", "fintech startup"],
        "v2ex": ["finance", "create"],
    },
    {
        "keywords": ["parent", "育儿", "宝宝", "带娃", "妈妈", "爸爸", "toddler", "baby", "child"],
        "reddit": ["Parenting", "Mommit", "daddit", "NewParents", "beyondthebump"],
        "hn": [],
        "v2ex": ["life", "share"],
    },
    {
        "keywords": ["developer", "programmer", "工程师", "程序员", "coding"],
        "reddit": ["SaaS", "Entrepreneur", "startups", "webdev", "programming", "SideProject"],
        "hn": ["saas founder", "indie hacker", "developer tools"],
        "v2ex": ["programmer", "create", "cloud"],
    },
    {
        "keywords": ["game", "游戏", "gamedev", "indie game", "独立游戏", "steam", "unity", "godot"],
        "reddit": ["gamedev", "IndieGaming", "Unity3D", "godot", "SideProject"],
        "hn": ["indie game", "game developer"],
        "v2ex": ["create", "share"],
    },
    {
        "keywords": ["design", "设计师", "ui", "ux", "figma", "creative"],
        "reddit": ["userexperience", "UI_Design", "graphic_design", "freelance"],
        "hn": ["design tools", "ux design"],
        "v2ex": ["create", "share"],
    },
    {
        "keywords": ["writer", "写作", "自媒体", "newsletter", "content", "博主"],
        "reddit": ["freelanceWriters", "Blogging", "content_marketing", "Entrepreneur"],
        "hn": ["newsletter", "content creator"],
        "v2ex": ["create", "share"],
    },
    {
        "keywords": ["fitness", "健身", "减肥", "health", "跑步", "营养"],
        "reddit": ["Fitness", "loseit", "nutrition", "running", "bodyweightfitness"],
        "hn": [],
        "v2ex": ["life"],
    },
    {
        "keywords": ["student", "学生", "考研", "留学", "career", "求职", "面试", "job"],
        "reddit": ["jobs", "cscareerquestions", "ApplyingToCollege", "gradadmissions"],
        "hn": ["job search", "career advice"],
        "v2ex": ["career", "jobs"],
    },
    {
        "keywords": ["teacher", "教师", "教育", "edtech", "homework", "课堂"],
        "reddit": ["Teachers", "education", "homeschool"],
        "hn": ["edtech"],
        "v2ex": ["share"],
    },
    {
        "keywords": ["pet", "猫", "狗", "宠物", "dog", "cat"],
        "reddit": ["dogs", "cats", "puppy101", "Dogtraining"],
        "hn": [],
        "v2ex": ["pet"],
    },
    {
        "keywords": ["travel", "旅行", "digital nomad", "远程", "nomad"],
        "reddit": ["travel", "solotravel", "digitalnomad", "onebag"],
        "hn": ["digital nomad"],
        "v2ex": ["life"],
    },
]

GENERIC_PAIN_KEYWORDS = {
    "cost/pricing": ["expensive", "cost", "price", "afford", "budget", "subscription", "贵", "省钱", "预算"],
    "time/friction": ["waste time", "slow", "tedious", "manual", "hours", "繁琐", "耗时", "效率"],
    "confusion": ["confused", "overwhelmed", "don't know", "how do i", "迷茫", "不知道", "怎么选"],
    "tools/workflow": ["tool", "app", "spreadsheet", "workflow", "integrate", "api", "工具", "软件"],
    "quality/trust": ["scam", "fake", "unreliable", "doesn't work", "坑", "不靠谱", "没用"],
    "learning curve": ["learn", "beginner", "tutorial", "steep", "入门", "学不会"],
    "support/community": ["lonely", "no one", "advice", "help me", "求助", "没人"],
}

# These classifiers deliberately remain local and inspect only public post text.  They
# are evidence labels, not claims about an author's identity or motives.
INTENT_PATTERNS: dict[str, list[str]] = {
    "promotion": [
        r"\b(i|we) (built|made|launched|created)\b", r"\bcheck out (my|our)\b",
        r"\b(use|try) my (app|tool|product)\b", r"\bdiscount code\b", r"我做了", r"我们做了", r"产品发布",
    ],
    "purchase_intent": [
        r"\bwilling to pay\b", r"\bworth paying\b", r"\b(?:my )?budget\b",
        r"\bunder \$?\d+\b", r"\bpaid for\b", r"愿意付费", r"预算", r"多少钱", r"值得付费",
    ],
    "alternative_search": [
        r"\balternative to\b", r"\breplacement for\b", r"\banything like\b",
        r"\blooking for an? alternative\b", r"替代品", r"有什么替代", r"替换.*工具",
    ],
    "recommendation_request": [
        r"\b(?:can you )?recommend\b", r"\bwhat do you use\b", r"\blooking for (?:an? )?(?:tool|app|service)\b",
        r"\bsuggestions?\b", r"求推荐", r"大家用什么", r"有什么好用",
    ],
    "switching_story": [
        r"\bswitched from\b", r"\bmigrat(?:ed|ing) from\b", r"\bcancell?ed\b",
        r"\bgave up (?:on|using)\b", r"\bstopped using\b", r"从.*换到", r"不再使用", r"取消订阅",
    ],
    "workaround_share": [
        r"\bworkaround\b", r"\bcurrent setup\b", r"\bended up using\b",
        r"\bcopy(?:ing)? (?:and )?paste\b", r"\bspreadsheet\b", r"临时方案", r"目前只能", r"手工", r"复制粘贴",
    ],
    "help_request": [
        r"\bhelp(?: me)?\b", r"\bhow (?:do|can) i\b", r"\bany advice\b",
        r"\bwhat should i do\b", r"求助", r"怎么办", r"请教", r"如何(?:做|解决)",
    ],
    "complaint": [
        r"\bhate\b", r"\bfrustrat\w*\b", r"\bannoying\b", r"\bstruggl\w*\b",
        r"\b(?:too |so )?(?:hard|difficult|broken|slow)\b", r"\bdoesn'?t work\b",
        r"太难", r"很烦", r"痛苦", r"不好用", r"失效", r"崩溃",
    ],
    "meta_discussion": [
        r"\bunpopular opinion\b", r"\bhot take\b", r"\bthe industry\b", r"\bthis community\b",
        r"行业.*讨论", r"社区.*讨论", r"大家怎么看",
    ],
}

INTENT_ORDER = [
    "promotion", "purchase_intent", "alternative_search", "recommendation_request",
    "switching_story", "workaround_share", "help_request", "complaint", "meta_discussion",
]

CURRENT_SOLUTION_PATTERNS = [
    r"(?:using|use|current setup is|currently on)\s+([A-Za-z0-9][A-Za-z0-9 .+/_-]{1,50})",
    r"(?:正在使用|目前用|现在用)\s*([^，。！？\n]{2,40})",
]
SWITCHING_TRIGGER_PATTERNS = [
    r"(?:because|due to)\s+([^.!?\n]{3,100})",
    r"(?:因为|由于)\s*([^，。！？\n]{3,60})",
]
DESIRED_OUTCOME_PATTERNS = [
    r"\b(?:looking for|need|want|wish)\s+(?:an?\s+)?([^.!?\n]{3,120})",
    r"(?:想要|需要|希望)\s*([^，。！？\n]{3,80})",
]
FAILED_ATTEMPT_PATTERNS = [
    r"\b(?:tried|attempted|already tried)\s+([^.!?\n]{3,120})",
    r"(?:试过|尝试过)\s*([^，。！？\n]{3,80})",
]

ROLE_KEYWORDS: dict[str, list[str]] = {
    "founder": ["founder", "startup", "saas", "创业", "创始人"],
    "developer": ["developer", "programmer", "coding", "api", "开发", "程序员"],
    "marketer": ["marketing", "growth", "seo", "广告", "营销", "增长"],
    "product_manager": ["product manager", "roadmap", "用户反馈", "产品经理"],
    "consumer": ["parent", "fitness", "travel", "个人", "用户"],
}

PROBLEM_STAGE_BY_INTENT = {
    "complaint": "problem_report", "help_request": "problem_report",
    "alternative_search": "solution_search", "recommendation_request": "solution_search",
    "purchase_intent": "solution_search", "switching_story": "solution_switching",
    "workaround_share": "workaround", "promotion": "solution_promotion",
    "meta_discussion": "context_discussion",
}

PULLPUSH = "https://api.pullpush.io/reddit/search/submission/"
BLOCKED_PAGE_PATTERNS = (
    "whoa there, pardner", "network policy", "access denied", "blocked by",
    "reddit edge block", "temporarily blocked",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def has_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _host_for(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def _open_circuit(url: str, reason: str) -> None:
    host = _host_for(url)
    if host:
        _SOURCE_CIRCUITS[host] = reason


def _circuit_reason(url: str) -> str | None:
    return _SOURCE_CIRCUITS.get(_host_for(url))


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(value) - utc_now()).total_seconds())
        except (TypeError, ValueError):
            return None


def _pace_source(host: str) -> None:
    elapsed = time.monotonic() - _SOURCE_LAST_REQUEST.get(host, 0.0)
    wait = SOURCE_MIN_INTERVAL_SECONDS - elapsed
    if wait > 0:
        time.sleep(wait)


def _http_get(url: str, *, timeout: int, accept: str) -> bytes:
    """Fetch conservatively: pace hosts, retry transient failures, and stop on blocks."""
    host = _host_for(url)
    if reason := _circuit_reason(url):
        raise SourceCircuitOpen(host, reason)
    request = urllib.request.Request(url, headers={
        "User-Agent": HTTP_USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6",
    })
    for attempt in range(HTTP_MAX_RETRIES + 1):
        _pace_source(host)
        _SOURCE_LAST_REQUEST[host] = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 429:
                _open_circuit(url, "circuit_open_after_429")
                raise
            if error.code == 403:
                _open_circuit(url, "circuit_open_after_403")
                raise
            if error.code not in HTTP_RETRYABLE_CODES or attempt == HTTP_MAX_RETRIES:
                raise
        except urllib.error.URLError:
            if attempt == HTTP_MAX_RETRIES:
                raise
        # ponytail: one bounded retry protects public services without turning
        # a temporary failure into a request storm; increase only with a source SLA.
        time.sleep(min(4.0, 1.0 * (2 ** attempt)))
    raise RuntimeError("unreachable retry state")


def http_get_json(url: str, timeout: int = 60) -> Any:
    return json.loads(_http_get(url, timeout=timeout, accept="application/json, */*;q=0.1").decode("utf-8"))


def http_get_text(url: str, timeout: int = 90) -> str:
    return _http_get(url, timeout=timeout, accept="text/plain, text/html;q=0.9, */*;q=0.1").decode("utf-8", errors="replace")


def clean_text(text: str, limit: int = 500) -> str:
    if not text or text in ("[removed]", "[deleted]"):
        return ""
    return re.sub(r"\s+", " ", text).strip()[:limit]


def tag_pain_themes(title: str, body: str = "", extra_keywords: dict[str, list[str]] | None = None) -> list[str]:
    blob = f"{title} {body}".lower()
    kws = dict(GENERIC_PAIN_KEYWORDS)
    if extra_keywords:
        kws.update(extra_keywords)
    hits = [cat for cat, words in kws.items() if any(w.lower() in blob for w in words)]
    return hits or ["general"]


def _matches(text: str, patterns: list[str]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE))


def classify_post_intent(title: str, body: str = "") -> dict[str, Any]:
    """Return a transparent, rule-based intent label for public post text."""
    text = f"{title}\n{body}".strip()
    if not text:
        return {
            "post_intent": "unknown", "intent_confidence": 0.0,
            "classification_method": "rule", "classification_version": "intent-v1",
        }

    for intent in INTENT_ORDER:
        matches = _matches(text, INTENT_PATTERNS[intent])
        if matches:
            return {
                "post_intent": intent,
                "intent_confidence": round(min(0.95, 0.62 + matches * 0.14), 2),
                "classification_method": "rule",
                "classification_version": "intent-v1",
            }
    return {
        "post_intent": "unknown", "intent_confidence": 0.0,
        "classification_method": "rule", "classification_version": "intent-v1",
    }


def _first_capture(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1), 120) or None
    return None


def _all_captures(text: str, patterns: list[str]) -> list[str]:
    captures = []
    for pattern in patterns:
        captures.extend(clean_text(match, 120) for match in re.findall(pattern, text, flags=re.IGNORECASE))
    return list(dict.fromkeys(capture for capture in captures if capture))[:5]


def extract_commercial_signals(title: str, body: str, intent: str) -> dict[str, Any]:
    """Extract observable solution-search signals; unknown stays unknown."""
    text = f"{title}\n{body}".strip()
    budget = bool(re.search(r"\b(?:budget|under \$?\d+|\$\d+)\b|预算|多少钱", text, re.IGNORECASE))
    explicit_wtp = bool(re.search(r"\bwilling to pay\b|\bworth paying\b|愿意付费|值得付费", text, re.IGNORECASE))
    implicit_wtp = intent in {"purchase_intent", "alternative_search", "recommendation_request"}
    return {
        "budget_mentioned": budget,
        "willingness_to_pay": "explicit" if explicit_wtp else ("implicit" if implicit_wtp else "unknown"),
        "current_solution": _first_capture(text, CURRENT_SOLUTION_PATTERNS),
        "alternative_sought": bool(_matches(text, INTENT_PATTERNS["alternative_search"])),
        "switching_trigger": _first_capture(text, SWITCHING_TRIGGER_PATTERNS)
        if intent == "switching_story" else None,
        "workaround_present": intent == "workaround_share" or bool(re.search(
            r"\b(?:manual|spreadsheet|copy(?:ing)? (?:and )?paste)\b|手工|临时方案|复制粘贴", text, re.IGNORECASE
        )),
    }


def evidence_labels(title: str, body: str, intent: str) -> tuple[str, list[str]]:
    """Classify evidence provenance without judging people or hidden account history."""
    text = f"{title}\n{body}".strip()
    flags: list[str] = []
    if intent == "promotion":
        flags.append("possible_self_promotion")
    if not body:
        flags.append("missing_body")
    if len(text) < 40:
        flags.append("low_context")
    if re.search(r"\b(?:works fine|no problem with|already solved|don't need)\b|没问题|不需要", text, re.IGNORECASE):
        return "counter_evidence", flags
    if intent == "promotion":
        return "commercially_contaminated", flags
    if intent in {"complaint", "help_request", "alternative_search", "recommendation_request", "workaround_share", "switching_story", "purchase_intent"}:
        return "primary_evidence", flags
    return "context_evidence", flags


def enrich_post(post: dict[str, Any], body_fields: tuple[str, ...] = ("selftext", "story_text", "title")) -> dict[str, Any]:
    """Add backward-compatible research fields to a normalized post record."""
    title = str(post.get("title") or "")
    body = ""
    for field in body_fields:
        if field != "title" and post.get(field):
            body = str(post[field])
            break
    intent = classify_post_intent(title, body)
    evidence_type, risk_flags = evidence_labels(title, body, intent["post_intent"])
    post.update(intent)
    post["problem_stage"] = PROBLEM_STAGE_BY_INTENT.get(intent["post_intent"], "unknown")
    post["commercial_signals"] = extract_commercial_signals(title, body, intent["post_intent"])
    post["evidence_type"] = evidence_type
    post["risk_flags"] = risk_flags
    post["pain_statement"] = clean_text(body or title, 280) or None
    post["desired_outcome"] = _first_capture(f"{title}\n{body}", DESIRED_OUTCOME_PATTERNS)
    post["failed_attempts"] = _all_captures(f"{title}\n{body}", FAILED_ATTEMPT_PATTERNS)
    post["source_snapshot"] = {
        "url": post.get("url"), "data_source": post.get("data_source"), "captured_at": utc_now().isoformat(),
    }
    post.setdefault("pain_themes", tag_pain_themes(title, body))
    return post


def annotate_comment_evidence(post: dict[str, Any]) -> None:
    """Label only observable confirmation in fetched public top-comment snippets."""
    evidence = []
    for phrase in post.get("top_comment_phrases", []):
        if not phrase:
            continue
        kind = "supporting_evidence" if re.search(
            r"\b(?:same here|me too|i also|also have|this is exactly)\b|同感|我也是|也遇到", phrase, re.IGNORECASE
        ) else "comment_context"
        evidence.append({"text": phrase, "evidence_type": kind})
    post["comment_evidence"] = evidence


def post_matches_intents(post: dict[str, Any], intents: str | None) -> bool:
    if not intents:
        return True
    allowed = {intent.strip() for intent in intents.split(",") if intent.strip()}
    return post.get("post_intent") in allowed


def post_score(post: dict) -> int:
    return max(int(post.get("score") or 0), int(post.get("ups") or 0))


def intent_query_plan(target: str, language: str) -> dict[str, list[str]]:
    """Keep intent query expansion explicit so callers can opt into extra requests."""
    base = target[:80].strip()
    if language == "zh":
        return {
            "complaint": [f"{base} 很难", f"{base} 痛点"],
            "recommendation_request": [f"{base} 求推荐"],
            "alternative_search": [f"{base} 替代品"],
            "switching_story": [f"{base} 不再使用"],
            "purchase_intent": [f"{base} 愿意付费", f"{base} 预算"],
        }
    return {
        "complaint": [f"{base} frustrating", f"{base} struggle"],
        "recommendation_request": [f"{base} what do you use"],
        "alternative_search": [f"{base} alternative"],
        "switching_story": [f"{base} switched from"],
        "purchase_intent": [f"{base} worth paying", f"{base} budget"],
    }


def infer_communities(target: str) -> dict[str, Any]:
    blob = target.lower()
    reddit: list[str] = []
    hn: list[str] = []
    v2ex: list[str] = []
    matched: list[str] = []

    for hint in COMMUNITY_HINTS:
        if any(k.lower() in blob for k in hint["keywords"]):
            matched.extend(hint["keywords"][:2])
            for s in hint["reddit"]:
                if s not in reddit:
                    reddit.append(s)
            for q in hint["hn"]:
                if q not in hn:
                    hn.append(q)
            for n in hint["v2ex"]:
                if n not in v2ex:
                    v2ex.append(n)

    target_profile = parse_target(target)
    languages = target_profile["languages"]
    lang = languages[0]
    if lang == "zh" and not v2ex:
        v2ex = ["create", "career", "programmer", "life"]

    if not reddit:
        # Fallback: tokenize target into plausible sub names (Agent should refine)
        tokens = re.findall(r"[a-zA-Z]{4,}", target)
        reddit = tokens[:5] if tokens else ["Entrepreneur", "AskReddit"]

    if not hn and "en" in languages:
        hn = [target[:80]]

    browser_urls = [
        f"https://old.reddit.com/search/?q={urllib.parse.quote(target)}&sort=top&t=week",
        f"https://hn.algolia.com/?q={urllib.parse.quote(target)}&sort=byDate",
    ]
    if lang == "zh":
        browser_urls.append(f"https://www.v2ex.com/go/create?q={urllib.parse.quote(target)}")

    return {
        "target": target,
        "language": lang,
        "languages": languages,
        "relevance_lexicon": target_profile["relevance_lexicon"],
        "confidence": "high" if matched else "low",
        "matched_keywords": list(dict.fromkeys(matched))[:6],
        "reddit_subs": reddit[:12],
        "hn_queries": hn[:3],
        "intent_queries": intent_query_plan(target, "en" if "en" in languages else lang),
        "v2ex_nodes": v2ex[:4],
        "browser_fallback_urls": browser_urls,
        "note": "Agent may override subs/queries; verify sub names exist before scan.",
    }


def fetch_reddit_posts(sub: str, limit: int = 100) -> list[dict]:
    key = (sub.lower(), limit)
    if key in _REDDIT_POST_CACHE:
        return _REDDIT_POST_CACHE[key]
    params = urllib.parse.urlencode({"subreddit": sub, "limit": limit, "sort": "desc"})
    url = f"{ARCTIC_POSTS}?{params}"
    try:
        posts = http_get_json(url).get("data", [])
    except urllib.error.HTTPError as e:
        if e.code == 422 and limit > 50:
            params = urllib.parse.urlencode({"subreddit": sub, "limit": 50, "sort": "desc"})
            posts = http_get_json(f"{ARCTIC_POSTS}?{params}").get("data", [])
        else:
            raise
    _REDDIT_POST_CACHE[key] = posts
    return posts


def fetch_reddit_comments(post_id: str, limit: int = 100) -> list[dict]:
    key = (post_id, limit)
    if key in _REDDIT_COMMENT_CACHE:
        return _REDDIT_COMMENT_CACHE[key]
    params = urllib.parse.urlencode({"link_id": f"t3_{post_id}", "limit": limit})
    url = f"{ARCTIC_COMMENTS}?{params}"
    try:
        comments = http_get_json(url).get("data", [])
    except urllib.error.HTTPError:
        comments = []
    _REDDIT_COMMENT_CACHE[key] = comments
    return comments


def fetch_reddit_pullpush(sub: str, after: int, size: int = 50) -> list[dict]:
    params = urllib.parse.urlencode({
        "subreddit": sub,
        "size": size,
        "sort": "desc",
        "sort_type": "created_utc",
        "after": after,
    })
    try:
        data = http_get_json(f"{PULLPUSH}?{params}")
        return data if isinstance(data, list) else data.get("data", [])
    except Exception:
        return []


def _source_error_status(error: Exception) -> tuple[str, str]:
    """Turn transport failures into actionable source states, never a fake empty result."""
    if isinstance(error, SourceCircuitOpen):
        return "rate_limited" if error.reason.endswith("429") else "unavailable", error.reason
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 403:
            return "unavailable", "403_network_policy"
        if error.code == 429:
            return "rate_limited", "429_rate_limit"
        if error.code == 422:
            return "degraded", "422_invalid_or_unstable_query"
        return "unavailable", f"http_{error.code}"
    return "unavailable", type(error).__name__


def _source_health(events: list[dict[str, Any]], source: str, post_count: int, *, enabled: bool = True) -> dict[str, str]:
    if not enabled:
        return {"status": "skipped", "reason": "disabled_by_cli"}
    relevant = [event for event in events if event.get("source") == source]
    failed = next((event for event in relevant if event.get("status") in {"unavailable", "rate_limited"}), None)
    if failed:
        return {"status": str(failed["status"]), "reason": str(failed.get("reason") or "request_failed")}
    if post_count:
        return {"status": "ok", "reason": f"{post_count}_qualified_posts"}
    if relevant:
        return {"status": "degraded", "reason": "no_qualified_posts_after_collection_or_thresholds"}
    return {"status": "empty", "reason": "no_collection_attempt"}


def browser_read_url(url: str, max_chars: int = 8000) -> dict[str, Any]:
    """Login-free page read via Jina Reader."""
    jina_url = JINA_READER.format(url=urllib.parse.quote(url, safe=""))
    if reason := _circuit_reason(jina_url):
        return {"ok": False, "url": url, "via": "r.jina.ai", "error_class": reason,
                "error": "Jina Reader is paused for this run after a terminal response."}
    try:
        text = http_get_text(jina_url)
        if any(pattern in text.lower() for pattern in BLOCKED_PAGE_PATTERNS):
            return {
                "ok": False, "url": url, "via": "r.jina.ai", "text": text[:max_chars],
                "error_class": "reddit_edge_block", "error": "Jina returned a known Reddit/network block page.",
            }
        return {"ok": True, "url": url, "via": "r.jina.ai", "text": text[:max_chars]}
    except Exception as e:
        status, reason = _source_error_status(e)
        if isinstance(e, urllib.error.HTTPError) and e.code in {403, 429}:
            _open_circuit(jina_url, "circuit_open_after_429" if e.code == 429 else "circuit_open_after_403")
        return {"ok": False, "url": url, "via": "r.jina.ai", "error_class": reason,
                "error": str(e), "source_status": status}


def top_comment_phrases(comments: list[dict], n: int = 3) -> list[str]:
    valid = [
        c for c in comments
        if c.get("body") and c["body"] not in ("[removed]", "[deleted]")
    ]
    top = sorted(valid, key=lambda c: int(c.get("score") or 0), reverse=True)[:n]
    return [clean_text(c["body"], 120) for c in top]


def heat_index(posts_72h: int, comments_72h: int, score_72h: int, active_ge3: int) -> float:
    return round(posts_72h * 2 + comments_72h / 4 + score_72h / 30 + active_ge3 * 3, 1)


def _member_tier(members: int) -> str:
    if members >= 100_000:
        return "large_broad"
    if members >= 10_000:
        return "medium_vertical"
    return "small_expert"


def _rule_summary(sub: str, fetch_rules: bool) -> tuple[dict[str, str], str, list[str]]:
    if not fetch_rules:
        return {}, "unknown", []
    result = browser_read_url(f"https://old.reddit.com/r/{sub}/about/rules/", max_chars=12000)
    if not result.get("ok"):
        return {}, "unknown", ["rules_unavailable"]
    text = str(result.get("text") or "")
    lower = text.lower()
    summary: dict[str, str] = {}
    for key, words in {
        "self_promotion": ["self-promotion", "self promotion", "promotion"],
        "surveys": ["survey", "questionnaire"],
        "product_links": ["product link", "affiliate", "referral"],
        "ai_content": ["ai-generated", "ai generated"],
    }.items():
        if any(word in lower for word in words):
            summary[key] = "mentioned_in_public_rules"
    if not summary.get("self_promotion"):
        return summary, "unknown", []
    if "weekly" in lower or "megathread" in lower:
        return summary, "weekly_thread_only", []
    if any(word in lower for word in ["prohibit", "not allowed", "not permit", "banned"]):
        return summary, "restricted", []
    return summary, "context_required", []


def _profile_roles(posts: list[dict[str, Any]]) -> list[str]:
    sample = " ".join(f"{p.get('title', '')} {p.get('selftext', '')}" for p in posts).lower()
    roles = [role for role, words in ROLE_KEYWORDS.items() if any(word.lower() in sample for word in words)]
    return roles[:4]


def build_community_profile(sub: str, limit: int = 30, fetch_rules: bool = True) -> dict[str, Any]:
    """Profile a public Reddit community from a recent sample and public rules page."""
    posts = fetch_reddit_posts(sub, limit=limit)
    members = int(posts[0].get("subreddit_subscribers") or 0) if posts else None
    enriched = [enrich_post({
        "title": p.get("title", ""), "selftext": clean_text(p.get("selftext", ""), 800),
    }) for p in posts]
    intent_counts = Counter(p["post_intent"] for p in enriched)
    direct_intents = {"complaint", "help_request", "alternative_search", "recommendation_request", "workaround_share", "switching_story", "purchase_intent"}
    styles = []
    for label, intents in {
        "help_seeking": {"help_request", "recommendation_request"},
        "solution_search": {"alternative_search", "purchase_intent", "switching_story"},
        "build_in_public": {"promotion"},
        "workaround_sharing": {"workaround_share"},
    }.items():
        if any(intent_counts[intent] for intent in intents):
            styles.append(label)
    strengths = []
    if any(intent_counts[i] for i in direct_intents):
        strengths.append("problem_discovery")
    if any(intent_counts[i] for i in {"alternative_search", "recommendation_request", "purchase_intent", "switching_story"}):
        strengths.append("purchase_validation")
    if intent_counts["promotion"]:
        strengths.append("solution_feedback")
    risks = []
    if intent_counts["promotion"]:
        risks.append("self_promotion")
    if len(posts) < 5:
        risks.append("small_recent_sample")
    rules_summary, commercial_policy, rule_flags = _rule_summary(sub, fetch_rules)
    profile = CommunityProfile(
        platform="reddit",
        community=f"r/{sub}",
        title=None,
        description=None,
        members=members,
        audience_roles=_profile_roles(posts),
        common_post_types=[name for name, _ in intent_counts.most_common(5) if name != "unknown"],
        discussion_style=styles,
        rules_summary=rules_summary,
        commercial_content_policy=commercial_policy,
        research_strengths=strengths,
        bias_risks=risks,
        activity_metrics={
            "sample_posts": len(posts),
            "sample_comments": sum(int(p.get("num_comments") or 0) for p in posts),
            "direct_evidence_ratio": round(
                sum(1 for p in enriched if p["post_intent"] in direct_intents) / len(enriched), 2
            ) if enriched else 0.0,
        },
        profile_fetched_at=utc_now().isoformat(),
        source_urls=[f"{ARCTIC_POSTS}?subreddit={urllib.parse.quote(sub)}"] + (
            [f"https://old.reddit.com/r/{sub}/about/rules/"] if fetch_rules else []
        ),
    )
    return {
        **profile.to_dict(),
        "member_tier": _member_tier(members) if members is not None else "unknown",
        "risk_flags": rule_flags,
        "classification_method": "public_sample+rule",
        "classification_version": "community-profile-v1",
    }


def assess_community(profile: dict[str, Any], target: str) -> dict[str, str]:
    """Expose separate research judgments; intentionally do not calculate a composite score."""
    target_terms = set(re.findall(r"[a-zA-Z]{4,}", target.lower()))
    target_roles = {
        role for role, words in ROLE_KEYWORDS.items()
        if any(word.lower() in target.lower() for word in words)
    }
    sample_text = " ".join(profile.get("audience_roles", []) + profile.get("common_post_types", [])).lower()
    relevance = "high" if target_roles & set(profile.get("audience_roles", [])) else (
        "medium" if target_terms and any(term in sample_text for term in target_terms) else "unknown"
    )
    sample_posts = int(profile.get("activity_metrics", {}).get("sample_posts") or 0)
    activity = "high" if sample_posts >= 20 else ("medium" if sample_posts >= 5 else "low")
    research_fit = "high" if profile.get("research_strengths") else "unknown"
    ratio = float(profile.get("activity_metrics", {}).get("direct_evidence_ratio") or 0)
    signal_quality = "high" if ratio >= 0.5 else ("medium" if ratio > 0 else "unknown")
    return {
        "relevance": relevance,
        "activity": activity,
        "research_fit": research_fit,
        "signal_quality": signal_quality,
    }


def _profile_cache_path(cache_dir: str, sub: str) -> Path:
    safe_sub = re.sub(r"[^a-zA-Z0-9_-]", "_", sub.lower())
    return Path(cache_dir) / f"reddit-{safe_sub}.json"


def load_or_build_community_profile(
    sub: str, *, limit: int, fetch_rules: bool, cache_dir: str, refresh: bool,
) -> tuple[dict[str, Any], bool]:
    """Cache public profile snapshots locally; a cache miss never changes research logic."""
    cache_path = _profile_cache_path(cache_dir, sub)
    if not refresh:
        try:
            with cache_path.open(encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("cache_version") == "community-profile-v1":
                return cached["profile"], True
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    profile = build_community_profile(sub, limit=limit, fetch_rules=fetch_rules)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump({"cache_version": "community-profile-v1", "profile": profile}, f, ensure_ascii=False, indent=2)
    return profile, False


def discover_sub(sub: str, args: argparse.Namespace) -> dict | None:
    after = int(utc_now().timestamp() - args.hours * 3600)
    posts = fetch_reddit_posts(sub, limit=args.limit)
    recent = [p for p in posts if int(p.get("created_utc") or 0) >= after]
    if not recent:
        return None

    members = int(recent[0].get("subreddit_subscribers") or 0)
    comments = sum(int(p.get("num_comments") or 0) for p in recent)
    scores = sum(post_score(p) for p in recent)
    active = sum(1 for p in recent if int(p.get("num_comments") or 0) >= 3)
    avg_c = comments / len(recent) if recent else 0

    pain_counter = Counter()
    for p in recent:
        for t in tag_pain_themes(p.get("title", ""), p.get("selftext", "")):
            pain_counter[t] += 1

    top_posts = sorted(
        recent,
        key=lambda p: int(p.get("num_comments") or 0) * 4 + post_score(p),
        reverse=True,
    )[:5]

    qualified = (
        len(recent) >= args.min_posts
        and (comments >= args.min_comments_total or active >= args.min_active_threads)
    )

    return {
        "platform": "reddit",
        "community": f"r/{sub}",
        "subreddit": f"r/{sub}",
        "members": members,
        "member_tier": _member_tier(members),
        "member_threshold_met": members >= args.min_members,
        "posts_in_window": len(recent),
        "comments_in_window": comments,
        "avg_comments": round(avg_c, 1),
        "active_threads_ge3": active,
        "heat_index": heat_index(len(recent), comments, scores, active),
        "top_pain_themes": [f"{k} ({v})" for k, v in pain_counter.most_common(4)],
        "qualified": qualified,
        "example_posts": [
            {
                "title": p.get("title", ""),
                "score": post_score(p),
                "comments": int(p.get("num_comments") or 0),
                "url": f"https://www.reddit.com{p.get('permalink', '')}",
            }
            for p in top_posts
        ],
    }


def extract_from_sub(
    sub: str, args: argparse.Namespace, after: int, source_events: list[dict[str, Any]] | None = None,
) -> list[dict]:
    hits: list[dict] = []
    try:
        posts = fetch_reddit_posts(sub, limit=args.limit)
        if source_events is not None:
            source_events.append({"source": "arctic_shift", "status": "ok", "subreddit": sub, "candidate_count": len(posts)})
    except Exception as e:
        print(f"err r/{sub} arctic: {e}", file=sys.stderr)
        if source_events is not None:
            status, reason = _source_error_status(e)
            source_events.append({"source": "arctic_shift", "status": status, "reason": reason, "subreddit": sub})
        if args.use_pullpush:
            posts = fetch_reddit_pullpush(sub, after)
            print(f"fallback pullpush r/{sub}: {len(posts)} posts", file=sys.stderr)
            if source_events is not None:
                source_events.append({"source": "pullpush", "status": "ok" if posts else "empty", "subreddit": sub})
        else:
            return hits

    for p in posts:
        if int(p.get("created_utc") or 0) < after:
            continue
        score = post_score(p)
        comments = int(p.get("num_comments") or 0)
        if score < args.min_score or comments < args.min_comments:
            continue

        body = clean_text(p.get("selftext", ""), 800)
        item = {
            "platform": "reddit",
            "community": f"r/{sub}",
            "subreddit": f"r/{sub}",
            "id": p.get("id"),
            "author": p.get("author"),
            "title": p.get("title", ""),
            "url": f"https://www.reddit.com{p.get('permalink', '')}",
            "score": score,
            "comments": comments,
            "selftext": body,
            "flair": p.get("link_flair_text"),
            "posted": datetime.fromtimestamp(
                int(p.get("created_utc") or 0), tz=timezone.utc
            ).isoformat(),
            "pain_themes": tag_pain_themes(p.get("title", ""), body),
            "data_source": "arctic-shift",
        }

        enrich_post(item)
        if not post_matches_intents(item, args.intents):
            continue

        if args.fetch_comments:
            time.sleep(args.delay)
            phrases = top_comment_phrases(fetch_reddit_comments(p["id"]))
            if not phrases and args.browser_fallback:
                br = browser_read_url(item["url"])
                if br["ok"]:
                    item["data_source"] = "browser/jina"
                    item["browser_excerpt"] = clean_text(br["text"], 600)
            while len(phrases) < 3:
                phrases.append("")
            item["top_comment_phrases"] = phrases[:3]
        else:
            item["top_comment_phrases"] = ["", "", ""]

        annotate_comment_evidence(item)
        hits.append(item)
    return hits


def hn_search(
    query: str, args: argparse.Namespace, after: int, source_events: list[dict[str, Any]] | None = None,
) -> list[dict]:
    params = urllib.parse.urlencode({
        "query": query,
        "tags": "story",
        "hitsPerPage": args.limit,
        "numericFilters": f"created_at_i>{after}",
    })
    try:
        data = http_get_json(f"{HN_ALGOLIA}?{params}")
    except Exception as e:
        print(f"err hn '{query}': {e}", file=sys.stderr)
        if source_events is not None:
            status, reason = _source_error_status(e)
            source_events.append({"source": "hn_algolia", "status": status, "reason": reason, "query": query})
        return []
    if source_events is not None:
        source_events.append({"source": "hn_algolia", "status": "ok", "query": query, "candidate_count": len(data.get("hits", []))})

    hits_out: list[dict] = []
    for hit in data.get("hits", []):
        score = int(hit.get("points") or 0)
        comments = int(hit.get("num_comments") or 0)
        if score < args.min_score or comments < args.min_comments:
            continue
        object_id = hit.get("objectID", "")
        item = {
            "platform": "hackernews",
            "community": "Hacker News",
            "id": object_id,
            "author": hit.get("author"),
            "title": hit.get("title", ""),
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}",
            "score": score,
            "comments": comments,
            "posted": datetime.fromtimestamp(
                int(hit.get("created_at_i") or 0), tz=timezone.utc
            ).isoformat(),
            "story_text": clean_text(hit.get("story_text") or "", 500),
            "hn_discussion": f"https://news.ycombinator.com/item?id={object_id}",
            "data_source": "hn.algolia.com",
            "top_comment_phrases": ["", "", ""],
        }
        item = enrich_post(item)
        annotate_comment_evidence(item)
        if post_matches_intents(item, args.intents):
            hits_out.append(item)
    return hits_out


def v2ex_fetch(
    node: str | None, args: argparse.Namespace, source_events: list[dict[str, Any]] | None = None,
) -> list[dict]:
    try:
        if node:
            topics = http_get_json(
                f"{V2EX_NODE}?{urllib.parse.urlencode({'node_name': node, 'page': 1})}"
            )
        else:
            topics = http_get_json(V2EX_HOT)
    except Exception as e:
        print(f"err v2ex {node or 'hot'}: {e}", file=sys.stderr)
        if source_events is not None:
            status, reason = _source_error_status(e)
            source_events.append({"source": "v2ex", "status": status, "reason": reason, "node": node or "hot"})
        return []

    if not isinstance(topics, list):
        topics = []
    if source_events is not None:
        source_events.append({"source": "v2ex", "status": "ok", "node": node or "hot", "candidate_count": len(topics)})

    hits_out: list[dict] = []
    for t in topics[: args.limit]:
        replies = int(t.get("replies") or 0)
        if replies < args.min_comments:
            continue
        node_title = t.get("node", {}).get("title") if isinstance(t.get("node"), dict) else node
        item = {
            "platform": "v2ex",
            "community": node_title or node or "hot",
            "id": t.get("id"),
            "author": t.get("member", {}).get("username") if isinstance(t.get("member"), dict) else None,
            "title": t.get("title", ""),
            "url": f"https://www.v2ex.com/t/{t.get('id')}",
            "comments": replies,
            "score": replies,
            "member": t.get("member", {}).get("username") if isinstance(t.get("member"), dict) else None,
            "created": t.get("created"),
            "data_source": "v2ex.com/api",
            "top_comment_phrases": ["", "", ""],
        }
        item = enrich_post(item)
        annotate_comment_evidence(item)
        if post_matches_intents(item, args.intents):
            hits_out.append(item)
    return hits_out


def cmd_plan(args: argparse.Namespace) -> int:
    if args.subs:
        plan = infer_communities(args.target)
        plan["reddit_subs"] = [s.strip() for s in args.subs.split(",") if s.strip()]
        plan["override"] = "cli --subs"
    elif args.plan_json:
        with open(args.plan_json, encoding="utf-8") as f:
            plan = json.load(f)
    else:
        plan = infer_communities(args.target)

    if args.hn_query:
        plan["hn_queries"] = [q.strip() for q in args.hn_query.split("|") if q.strip()]
    if args.v2ex_node:
        plan["v2ex_nodes"] = [n.strip() for n in args.v2ex_node.split(",") if n.strip()]

    if args.profile_communities:
        plan["community_profiles"] = profile_plan_communities(plan, args.target, args)

    payload = {"command": "plan-communities", "schema_version": "2.1", "as_of": utc_now().isoformat(), "plan": plan}
    _write_out(payload, args.out)
    return 0


def profile_plan_communities(plan: dict[str, Any], target: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Attach cached public profiles to a plan without changing its candidate list."""
    profiles = []
    for index, sub in enumerate(plan.get("reddit_subs", [])):
        if index:
            time.sleep(args.delay)
        try:
            profile, cache_hit = load_or_build_community_profile(
                sub, limit=args.profile_limit, fetch_rules=not args.no_rules,
                cache_dir=args.cache_dir, refresh=args.refresh_profiles,
            )
            profile["research_assessment"] = assess_community(profile, target)
            profile["cache_hit"] = cache_hit
            profiles.append(profile)
        except Exception as e:
            profiles.append({
                "platform": "reddit", "community": f"r/{sub}", "error": str(e),
                "research_assessment": {
                    "relevance": "unknown", "activity": "unknown",
                    "research_fit": "unknown", "signal_quality": "unknown",
                },
            })
    return profiles


def cmd_profile_community(args: argparse.Namespace) -> int:
    args.community = args.community.removeprefix("r/")
    profile, cache_hit = load_or_build_community_profile(
        args.community, limit=args.limit, fetch_rules=not args.no_rules,
        cache_dir=args.cache_dir, refresh=args.refresh,
    )
    profile["cache_hit"] = cache_hit
    payload = {
        "command": "profile-community", "schema_version": "2.1",
        "as_of": utc_now().isoformat(), "profile": profile,
    }
    _write_out(payload, args.out)
    return 0


def _input_posts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    step_b = payload.get("step_b")
    if isinstance(step_b, dict) and isinstance(step_b.get("posts"), list):
        return step_b["posts"]
    return payload.get("posts", []) if isinstance(payload.get("posts"), list) else []


def _topic_matches(post: dict[str, Any], topic: str) -> bool:
    text = " ".join(str(post.get(field) or "") for field in ("title", "selftext", "story_text")).lower()
    normalized = topic.lower().strip()
    if normalized in text:
        return True
    english_terms = [term for term in re.findall(r"[a-zA-Z]{3,}", normalized) if term not in {"the", "and", "for", "with"}]
    return bool(english_terms) and all(term in text for term in english_terms)


def compare_communities(payload: dict[str, Any], topic: str) -> dict[str, Any]:
    """Describe observable agreements and differences without converting them to one score."""
    matches = [enrich_post(dict(post)) for post in _input_posts(payload) if _topic_matches(post, topic)]
    by_community: dict[str, list[dict[str, Any]]] = {}
    for post in matches:
        by_community.setdefault(str(post.get("community") or "unknown"), []).append(post)

    theme_communities: dict[str, set[str]] = {}
    differences = []
    for community, posts in sorted(by_community.items()):
        intents = Counter(str(post.get("post_intent") or "unknown") for post in posts)
        themes = Counter(theme for post in posts for theme in post.get("pain_themes", []))
        for theme in themes:
            theme_communities.setdefault(theme, set()).add(community)
        current_solutions = [
            post.get("commercial_signals", {}).get("current_solution") for post in posts
            if post.get("commercial_signals", {}).get("current_solution")
        ]
        evidence_types = Counter(str(post.get("evidence_type") or "context_evidence") for post in posts)
        differences.append({
            "community": community,
            "post_count": len(posts),
            "dominant_intents": [name for name, _ in intents.most_common(3)],
            "top_pain_themes": [name for name, _ in themes.most_common(4)],
            "common_current_solutions": list(dict.fromkeys(current_solutions))[:5],
            "evidence_types": dict(evidence_types),
            "sample_urls": [post.get("url") for post in posts[:3] if post.get("url")],
        })

    return {
        "topic": topic,
        "matched_posts": len(matches),
        "matched_communities": len(by_community),
        "shared_pains": sorted(theme for theme, communities in theme_communities.items() if len(communities) >= 2),
        "community_differences": differences,
        "interpretation": {
            "surface_problem": "See shared_pains and community_differences; no aggregate opportunity score is calculated.",
            "possible_root_problem": "unknown — requires human review of the cited evidence and counter-evidence.",
        },
    }


def cmd_compare_communities(args: argparse.Namespace) -> int:
    with open(args.input, encoding="utf-8") as f:
        payload = json.load(f)
    result = compare_communities(payload, args.topic)
    _write_out({
        "command": "compare-communities", "schema_version": "2.1",
        "as_of": utc_now().isoformat(), **result,
    }, args.out)
    return 0


def cmd_analyze_research(args: argparse.Namespace) -> int:
    with open(args.input, encoding="utf-8") as f:
        payload = json.load(f)
    result = analyze_research(payload)
    output = {"command": "analyze-research", "as_of": utc_now().isoformat(), **result}
    for key in ("research_scope", "window_hours", "filters", "source_health", "source_events", "quality_gate", "step_a", "plan"):
        if key in payload:
            output[key] = payload[key]
    _write_out(output, args.out)
    return 0


def cmd_render_report(args: argparse.Namespace) -> int:
    """Render a complete, source-linked Markdown report from a JSON result."""
    with open(args.input, encoding="utf-8") as f:
        payload = json.load(f)
    text = render_report(payload)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text, end="")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    subs = [s.strip() for s in args.subs.split(",") if s.strip()]
    results: list[dict] = []

    for i, sub in enumerate(subs):
        if i:
            time.sleep(args.delay)
        try:
            row = discover_sub(sub, args)
            if row:
                results.append(row)
                print(f"ok r/{sub}: {row['posts_in_window']} posts", file=sys.stderr)
            else:
                print(f"skip r/{sub}", file=sys.stderr)
        except Exception as e:
            print(f"err r/{sub}: {e}", file=sys.stderr)

    results.sort(key=lambda x: x["heat_index"], reverse=True)
    payload = {
        "command": "discover",
        "schema_version": "2.1",
        "platform": "reddit",
        "as_of": utc_now().isoformat(),
        "window_hours": args.hours,
        "data_source": "arctic-shift.photon-reddit.com",
        "subs_scanned": len(subs),
        "subs_with_posts": len(results),
        "qualified_subs": [r for r in results if r["qualified"]],
        "all_subs": results,
    }
    _write_out(payload, args.out)
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    subs = [s.strip() for s in args.subs.split(",") if s.strip()]
    after = int(utc_now().timestamp() - args.hours * 3600)
    hits: list[dict] = []

    for i, sub in enumerate(subs):
        if i:
            time.sleep(args.delay)
        sub_hits = extract_from_sub(sub, args, after)
        hits.extend(sub_hits)
        print(f"ok r/{sub}: {len(sub_hits)} hits", file=sys.stderr)

    hits.sort(key=lambda x: x.get("comments", 0) * 2 + x.get("score", 0), reverse=True)
    payload = {
        "command": "extract",
        "schema_version": "2.1",
        "as_of": utc_now().isoformat(),
        "window_hours": args.hours,
        "filters": {"min_score": args.min_score, "min_comments": args.min_comments, "intents": args.intents},
        "data_source": "arctic-shift.photon-reddit.com",
        "count": len(hits),
        "posts": hits,
    }
    _write_out(payload, args.out)
    return 0


def cmd_hn_search(args: argparse.Namespace) -> int:
    after = int(utc_now().timestamp() - args.hours * 3600)
    hits_out = hn_search(args.query, args, after)
    payload = {
        "command": "hn-search",
        "schema_version": "2.1",
        "platform": "hackernews",
        "as_of": utc_now().isoformat(),
        "query": args.query,
        "window_hours": args.hours,
        "data_source": "hn.algolia.com",
        "count": len(hits_out),
        "posts": hits_out,
    }
    _write_out(payload, args.out)
    return 0


def cmd_v2ex_hot(args: argparse.Namespace) -> int:
    hits_out = v2ex_fetch(args.node, args)
    payload = {
        "command": "v2ex-hot",
        "schema_version": "2.1",
        "platform": "v2ex",
        "as_of": utc_now().isoformat(),
        "node": args.node or "hot",
        "data_source": "v2ex.com/api",
        "count": len(hits_out),
        "posts": hits_out,
    }
    _write_out(payload, args.out)
    return 0


def cmd_browser_read(args: argparse.Namespace) -> int:
    result = browser_read_url(args.url, max_chars=args.max_chars)
    payload = {
        "command": "browser-read",
        "schema_version": "2.1",
        "platform": "browser",
        "as_of": utc_now().isoformat(),
        "result": result,
    }
    _write_out(payload, args.out)
    return 0


def _probe_json_source(name: str, url: str) -> dict[str, str]:
    try:
        data = http_get_json(url, timeout=20)
    except Exception as error:
        status, reason = _source_error_status(error)
        return {"status": status, "reason": reason}
    is_empty = data in ({}, [], None) or (isinstance(data, dict) and data.get("data") == [])
    return {"status": "empty" if is_empty else "ok", "reason": "probe_returned_no_records" if is_empty else "probe_ok"}


def diagnose_sources() -> dict[str, dict[str, str]]:
    """Probe each public route once so an agent can choose a viable collection plan."""
    # Arctic Shift accepts a practical listing size more reliably than `limit=1`.
    arctic_url = f"{ARCTIC_POSTS}?{urllib.parse.urlencode({'subreddit': 'SaaS', 'limit': 50, 'sort': 'desc'})}"
    pullpush_url = f"{PULLPUSH}?{urllib.parse.urlencode({'subreddit': 'SaaS', 'size': 1, 'sort': 'desc'})}"
    results = {
        "arctic_shift": _probe_json_source("arctic_shift", arctic_url),
        "reddit_public": _probe_json_source("reddit_public", "https://www.reddit.com/r/SaaS/top.json?t=week&limit=1"),
        "pullpush": _probe_json_source("pullpush", pullpush_url),
        "hn_algolia": _probe_json_source("hn_algolia", f"{HN_ALGOLIA}?query=indie%20hacker&hitsPerPage=1"),
        "v2ex": _probe_json_source("v2ex", V2EX_HOT),
    }
    jina = browser_read_url("https://old.reddit.com/r/SaaS/top/?t=week", max_chars=500)
    results["jina_old_reddit"] = {
        "status": "ok" if jina.get("ok") else "unavailable",
        "reason": "probe_ok" if jina.get("ok") else str(jina.get("error_class") or jina.get("error") or "request_failed"),
    }
    return results


def cmd_diagnose(args: argparse.Namespace) -> int:
    payload = {
        "command": "diagnose", "schema_version": "2.3", "as_of": utc_now().isoformat(),
        "source_health": diagnose_sources(),
        "note": "Use HN-first collection when Reddit routes are unavailable or degraded; source health is an environment observation, not a community-demand conclusion.",
    }
    _write_out(payload, args.out)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline: plan → discover → extract → HN/V2EX → combined JSON for Agent Step C."""
    if args.subs:
        plan = infer_communities(args.target)
        plan["reddit_subs"] = [s.strip() for s in args.subs.split(",") if s.strip()]
    elif args.plan_json:
        with open(args.plan_json, encoding="utf-8") as f:
            loaded_plan = json.load(f)
        plan = loaded_plan.get("plan", loaded_plan) if isinstance(loaded_plan, dict) else {}
    else:
        plan = infer_communities(args.target)

    if args.hn_query:
        plan["hn_queries"] = [q.strip() for q in args.hn_query.split("|") if q.strip()]
    if args.v2ex_node:
        plan["v2ex_nodes"] = [n.strip() for n in args.v2ex_node.split(",") if n.strip()]

    if args.profile_communities and not plan.get("community_profiles"):
        plan["community_profiles"] = profile_plan_communities(plan, args.target, args)

    subs = plan.get("reddit_subs", [])[: args.max_subs]
    after = int(utc_now().timestamp() - args.hours * 3600)

    # Step A: discover
    all_subs: list[dict] = []
    for i, sub in enumerate(subs):
        if i:
            time.sleep(args.delay)
        try:
            row = discover_sub(sub, args)
            if row:
                all_subs.append(row)
        except Exception as e:
            print(f"discover err r/{sub}: {e}", file=sys.stderr)

    qualified = [r for r in all_subs if r.get("qualified")]
    extract_targets = [
        s.replace("r/", "") for s in (
            [r["subreddit"] for r in qualified] if qualified else [f"r/{s}" for s in subs[:6]]
        )
    ]
    extract_targets = [t.replace("r/", "") for t in extract_targets]

    source_events: list[dict[str, Any]] = []

    # Step B: extract Reddit
    reddit_posts: list[dict] = []
    for i, sub in enumerate(extract_targets):
        if i:
            time.sleep(args.delay)
        reddit_posts.extend(extract_from_sub(sub, args, after, source_events))

    # Step B: HN supplement (English / SaaS / dev targets)
    hn_posts: list[dict] = []
    if not args.no_hn and plan.get("hn_queries"):
        hn_queries = list(plan["hn_queries"][:2])
        # Reddit failures are an environment condition, not a reason to hand users an
        # empty report.  Expand the existing, target-specific HN plan once instead.
        if len(reddit_posts) < 3 or args.intent_query_expansion:
            hn_queries.extend(
                queries[0] for queries in plan.get("intent_queries", {}).values() if queries
            )
        for q in list(dict.fromkeys(hn_queries))[:args.max_hn_queries]:
            time.sleep(args.delay)
            hn_posts.extend(hn_search(q, args, after, source_events))

    # Step B: V2EX supplement (Chinese targets)
    v2ex_posts: list[dict] = []
    if not args.no_v2ex and plan.get("v2ex_nodes"):
        for node in plan["v2ex_nodes"][:3]:
            time.sleep(args.delay)
            v2ex_posts.extend(v2ex_fetch(node, args, source_events))

    # Browser fallback if too few posts
    browser_notes: list[dict] = []
    total = len(reddit_posts) + len(hn_posts) + len(v2ex_posts)
    if total < args.min_total_posts and args.browser_fallback:
        for url in plan.get("browser_fallback_urls", [])[:2]:
            time.sleep(2)
            br = browser_read_url(url)
            browser_notes.append(br)
            source_events.append({
                "source": "jina_old_reddit", "status": "ok" if br.get("ok") else br.get("source_status", "unavailable"),
                "reason": br.get("error_class") or br.get("error"), "url": url,
            })
            print(f"browser fallback: {url} ok={br.get('ok')}", file=sys.stderr)
            if br.get("error_class") in {"429_rate_limit", "circuit_open_after_429", "circuit_open_after_403"}:
                break

    collected_posts = reddit_posts + hn_posts + v2ex_posts
    for post in collected_posts:
        post.update(classify_target_relevance(post, args.target))
    collected_posts.sort(key=lambda x: x.get("comments", 0) * 2 + x.get("score", 0), reverse=True)
    all_posts = [post for post in collected_posts if post.get("target_relevance") != "low"]
    noise_posts = [post for post in collected_posts if post.get("target_relevance") == "low"]
    source_health = {
        "arctic_shift": _source_health(source_events, "arctic_shift", len(reddit_posts)),
        "hn_algolia": _source_health(source_events, "hn_algolia", len(hn_posts), enabled=not args.no_hn),
        "v2ex": _source_health(source_events, "v2ex", len(v2ex_posts), enabled=not args.no_v2ex),
        "jina_old_reddit": _source_health(source_events, "jina_old_reddit", 0, enabled=bool(browser_notes)),
    }
    research_analysis = analyze_research({
        "target": args.target, "step_b": {"posts": collected_posts},
        "quality_gate": {"min_primary_evidence": args.min_primary_evidence},
    }) if args.analyze else None
    if research_analysis:
        all_posts = research_analysis["posts"]

    captured_at = utc_now().isoformat()
    payload = {
        "command": "run",
        "version": "2.3.1",
        "schema_version": "2.3" if research_analysis else "2.1",
        "as_of": captured_at,
        "target": args.target,
        "target_profile": parse_target(args.target),
        "research_scope": {
            "started_at": captured_at,
            "time_window_hours": args.hours,
            "platforms": ["reddit"] + ([] if args.no_hn else ["hackernews"]) + ([] if args.no_v2ex else ["v2ex"]),
            "login_required": False,
        },
        "plan": plan,
        "window_hours": args.hours,
        "filters": {"min_score": args.min_score, "min_comments": args.min_comments, "intents": args.intents},
        "step_a": {
            "qualified_communities": qualified,
            "all_communities": all_subs,
            "community_profiles": plan.get("community_profiles", []),
        },
        "step_b": {
            "posts_by_platform": {
                "reddit": len(reddit_posts),
                "hackernews": len(hn_posts),
                "v2ex": len(v2ex_posts),
            },
            "posts": all_posts,
            "noise_posts": noise_posts,
            "browser_fallback": browser_notes if browser_notes else None,
        },
        "source_events": source_events,
        "source_health": source_health,
        "quality_gate": {"min_primary_evidence": args.min_primary_evidence},
        "step_c_hint": "Agent: use the nine-section report contract; low-relevance posts and insufficient evidence cannot support product opportunities.",
        "analysis": research_analysis,
        "total_posts": len(all_posts),
        "total_collected_posts": len(collected_posts),
    }
    _write_out(payload, args.out)
    verdict = research_analysis.get("evidence_verdict", {}).get("status") if research_analysis else "NOT_ANALYZED"
    print(f"VERDICT: {verdict} | posts={len(all_posts)} relevant / {len(collected_posts)} collected | "
          f"reddit={len(reddit_posts)} hn={len(hn_posts)} v2ex={len(v2ex_posts)}", file=sys.stderr)
    return 2 if verdict == "INSUFFICIENT_EVIDENCE" else 0


def _write_out(payload: dict, path: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {path}", file=sys.stderr)
    else:
        print(text)


def _add_common_scan_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--hours", type=int, default=72)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--delay", type=float, default=1.2)
    p.add_argument("--min-members", type=int, default=10000)
    p.add_argument("--min-posts", type=int, default=3)
    p.add_argument("--min-comments-total", type=int, default=30)
    p.add_argument("--min-active-threads", type=int, default=5)
    p.add_argument("--min-score", type=int, default=50)
    p.add_argument("--min-comments", type=int, default=20)
    p.add_argument("--intents", default=None,
                   help="Comma-separated post intents to retain (for example complaint,alternative_search)")
    p.add_argument("--fetch-comments", action="store_true")
    p.add_argument("--browser-fallback", action="store_true", default=True)
    p.add_argument("--no-browser-fallback", action="store_false", dest="browser_fallback")
    p.add_argument("--use-pullpush", action="store_true", help="Last-resort Reddit fallback (may 429)")
    p.add_argument("--out", default=None)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pain Miner — domain-agnostic community scanner")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("plan-communities", help="Infer communities from target user description")
    pl.add_argument("--target", required=True)
    pl.add_argument("--subs", default=None, help="Override inferred Reddit subs (comma-separated)")
    pl.add_argument("--hn-query", default=None, help="Override HN queries (pipe-separated)")
    pl.add_argument("--v2ex-node", default=None, help="Override V2EX nodes (comma-separated)")
    pl.add_argument("--plan-json", default=None, help="Load plan from JSON file")
    pl.add_argument("--profile-communities", action="store_true",
                    help="Fetch public community profiles for inferred Reddit candidates")
    pl.add_argument("--profile-limit", type=int, default=30)
    pl.add_argument("--cache-dir", default=".pain-miner-cache/communities")
    pl.add_argument("--refresh-profiles", action="store_true")
    pl.add_argument("--no-rules", action="store_true", help="Skip public rules-page lookup during profiling")
    pl.add_argument("--delay", type=float, default=1.2)
    pl.add_argument("--out", default=None)
    pl.set_defaults(func=cmd_plan)

    pc = sub.add_parser("profile-community", help="Profile one public Reddit community")
    pc.add_argument("--platform", choices=["reddit"], default="reddit")
    pc.add_argument("--community", required=True, help="Subreddit name without r/")
    pc.add_argument("--limit", type=int, default=30)
    pc.add_argument("--cache-dir", default=".pain-miner-cache/communities")
    pc.add_argument("--refresh", action="store_true")
    pc.add_argument("--no-rules", action="store_true", help="Skip public rules-page lookup")
    pc.add_argument("--out", default=None)
    pc.set_defaults(func=cmd_profile_community)

    cc = sub.add_parser("compare-communities", help="Compare a topic across communities in an existing result JSON")
    cc.add_argument("--input", required=True, help="JSON output from run, extract, hn-search, or v2ex-hot")
    cc.add_argument("--topic", required=True, help="Topic phrase used to select evidence")
    cc.add_argument("--out", default=None)
    cc.set_defaults(func=cmd_compare_communities)

    ar = sub.add_parser("analyze-research", help="Build deduplication, pain signal panels, comparisons, and opportunity cards")
    ar.add_argument("--input", required=True, help="JSON output from run, extract, hn-search, or v2ex-hot")
    ar.add_argument("--out", default=None)
    ar.set_defaults(func=cmd_analyze_research)

    rr = sub.add_parser("render-report", help="Render a complete source-linked Markdown research report")
    rr.add_argument("--input", required=True, help="JSON output from run or analyze-research")
    rr.add_argument("--out", default=None, help="Markdown output path; prints to stdout if omitted")
    rr.set_defaults(func=cmd_render_report)

    r = sub.add_parser("run", help="Full pipeline: plan + discover + extract + supplements")
    r.add_argument("--target", required=True)
    r.add_argument("--subs", default=None)
    r.add_argument("--hn-query", default=None)
    r.add_argument("--v2ex-node", default=None)
    r.add_argument("--plan-json", default=None)
    r.add_argument("--max-subs", type=int, default=10)
    r.add_argument("--profile-communities", action="store_true",
                   help="Attach cached public profiles to Reddit candidates before collection")
    r.add_argument("--profile-limit", type=int, default=30)
    r.add_argument("--cache-dir", default=".pain-miner-cache/communities")
    r.add_argument("--refresh-profiles", action="store_true")
    r.add_argument("--no-rules", action="store_true", help="Skip public rules-page lookup during profiling")
    r.add_argument("--analyze", action="store_true", help="Attach structured pain clusters and opportunity cards to run output")
    r.add_argument("--intent-query-expansion", action="store_true",
                   help="Add intent-shaped HN queries from the generated plan")
    r.add_argument("--max-hn-queries", type=int, default=6,
                   help="Maximum HN queries when --intent-query-expansion is enabled")
    r.add_argument("--min-total-posts", type=int, default=5,
                   help="Trigger browser fallback if fewer posts found")
    r.add_argument("--min-primary-evidence", type=int, default=5,
                   help="Suppress opportunities and return exit code 2 below this many target-relevant primary posts")
    r.add_argument("--no-hn", action="store_true")
    r.add_argument("--no-v2ex", action="store_true")
    _add_common_scan_args(r)
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("discover", help="Scan subreddits for activity")
    d.add_argument("--subs", required=True)
    _add_common_scan_args(d)
    d.set_defaults(func=cmd_discover)

    e = sub.add_parser("extract", help="Extract hot posts meeting score/comment thresholds")
    e.add_argument("--subs", required=True)
    _add_common_scan_args(e)
    e.set_defaults(func=cmd_extract)

    h = sub.add_parser("hn-search", help="Search Hacker News (login-free)")
    h.add_argument("--query", required=True)
    h.add_argument("--hours", type=int, default=168)
    h.add_argument("--limit", type=int, default=50)
    h.add_argument("--min-score", type=int, default=50)
    h.add_argument("--min-comments", type=int, default=20)
    h.add_argument("--intents", default=None)
    h.add_argument("--out", default=None)
    h.set_defaults(func=cmd_hn_search)

    v = sub.add_parser("v2ex-hot", help="Fetch V2EX hot or node topics (login-free)")
    v.add_argument("--node", default=None)
    v.add_argument("--limit", type=int, default=30)
    v.add_argument("--min-comments", type=int, default=20)
    v.add_argument("--intents", default=None)
    v.add_argument("--out", default=None)
    v.set_defaults(func=cmd_v2ex_hot)

    b = sub.add_parser("browser-read", help="Read public page via Jina Reader (login-free)")
    b.add_argument("--url", required=True)
    b.add_argument("--max-chars", type=int, default=8000)
    b.add_argument("--out", default=None)
    b.set_defaults(func=cmd_browser_read)

    dg = sub.add_parser("diagnose", help="Probe public data-source health once before a research run")
    dg.add_argument("--out", default=None)
    dg.set_defaults(func=cmd_diagnose)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
