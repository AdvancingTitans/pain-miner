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
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import Any

ARCTIC_POSTS = "https://arctic-shift.photon-reddit.com/api/posts/search"
ARCTIC_COMMENTS = "https://arctic-shift.photon-reddit.com/api/comments/search"
HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"
V2EX_HOT = "https://www.v2ex.com/api/topics/hot.json"
V2EX_NODE = "https://www.v2ex.com/api/topics/show.json"
JINA_READER = "https://r.jina.ai/{url}"

# Keyword → community hints (expandable; Agent may override via --subs/--hn-query/--v2ex-node)
COMMUNITY_HINTS: list[dict[str, Any]] = [
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
        "keywords": ["developer", "programmer", "工程师", "程序员", "coding", "saas", "startup", "创业", "独立开发"],
        "reddit": ["SaaS", "Entrepreneur", "startups", "webdev", "programming", "SideProject"],
        "hn": ["saas founder", "indie hacker", "developer tools"],
        "v2ex": ["programmer", "create", "cloud", "career"],
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

PULLPUSH = "https://api.pullpush.io/reddit/search/submission/"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def has_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def http_get_json(url: str, timeout: int = 60) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "pain-miner/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def http_get_text(url: str, timeout: int = 90) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "pain-miner/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


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


def post_score(post: dict) -> int:
    return max(int(post.get("score") or 0), int(post.get("ups") or 0))


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

    lang = "zh" if has_chinese(target) else "en"
    if lang == "zh" and not v2ex:
        v2ex = ["create", "career", "programmer", "life"]

    if not reddit:
        # Fallback: tokenize target into plausible sub names (Agent should refine)
        tokens = re.findall(r"[a-zA-Z]{4,}", target)
        reddit = tokens[:5] if tokens else ["Entrepreneur", "AskReddit"]

    if not hn and lang == "en":
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
        "matched_keywords": list(dict.fromkeys(matched))[:6],
        "reddit_subs": reddit[:12],
        "hn_queries": hn[:3],
        "v2ex_nodes": v2ex[:4],
        "browser_fallback_urls": browser_urls,
        "note": "Agent may override subs/queries; verify sub names exist before scan.",
    }


def fetch_reddit_posts(sub: str, limit: int = 100) -> list[dict]:
    params = urllib.parse.urlencode({"subreddit": sub, "limit": limit, "sort": "desc"})
    url = f"{ARCTIC_POSTS}?{params}"
    try:
        return http_get_json(url).get("data", [])
    except urllib.error.HTTPError as e:
        if e.code == 422 and limit > 50:
            params = urllib.parse.urlencode({"subreddit": sub, "limit": 50, "sort": "desc"})
            return http_get_json(f"{ARCTIC_POSTS}?{params}").get("data", [])
        raise


def fetch_reddit_comments(post_id: str, limit: int = 100) -> list[dict]:
    params = urllib.parse.urlencode({"link_id": f"t3_{post_id}", "limit": limit})
    url = f"{ARCTIC_COMMENTS}?{params}"
    try:
        return http_get_json(url).get("data", [])
    except urllib.error.HTTPError:
        return []


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


def browser_read_url(url: str, max_chars: int = 8000) -> dict[str, Any]:
    """Login-free page read via Jina Reader."""
    jina_url = JINA_READER.format(url=urllib.parse.quote(url, safe=""))
    try:
        text = http_get_text(jina_url)
        return {"ok": True, "url": url, "via": "r.jina.ai", "text": text[:max_chars]}
    except Exception as e:
        return {"ok": False, "url": url, "via": "r.jina.ai", "error": str(e)}


def top_comment_phrases(comments: list[dict], n: int = 3) -> list[str]:
    valid = [
        c for c in comments
        if c.get("body") and c["body"] not in ("[removed]", "[deleted]")
    ]
    top = sorted(valid, key=lambda c: int(c.get("score") or 0), reverse=True)[:n]
    return [clean_text(c["body"], 120) for c in top]


def heat_index(posts_72h: int, comments_72h: int, score_72h: int, active_ge3: int) -> float:
    return round(posts_72h * 2 + comments_72h / 4 + score_72h / 30 + active_ge3 * 3, 1)


def discover_sub(sub: str, args: argparse.Namespace) -> dict | None:
    after = int(utc_now().timestamp() - args.hours * 3600)
    posts = fetch_reddit_posts(sub, limit=args.limit)
    recent = [p for p in posts if int(p.get("created_utc") or 0) >= after]
    if not recent:
        return None

    members = int(recent[0].get("subreddit_subscribers") or 0)
    if members < args.min_members:
        return None

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


def extract_from_sub(sub: str, args: argparse.Namespace, after: int) -> list[dict]:
    hits: list[dict] = []
    try:
        posts = fetch_reddit_posts(sub, limit=args.limit)
    except Exception as e:
        print(f"err r/{sub} arctic: {e}", file=sys.stderr)
        if args.use_pullpush:
            posts = fetch_reddit_pullpush(sub, after)
            print(f"fallback pullpush r/{sub}: {len(posts)} posts", file=sys.stderr)
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

        hits.append(item)
    return hits


def hn_search(query: str, args: argparse.Namespace, after: int) -> list[dict]:
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
        return []

    hits_out: list[dict] = []
    for hit in data.get("hits", []):
        score = int(hit.get("points") or 0)
        comments = int(hit.get("num_comments") or 0)
        if score < args.min_score or comments < args.min_comments:
            continue
        object_id = hit.get("objectID", "")
        hits_out.append({
            "platform": "hackernews",
            "community": "Hacker News",
            "id": object_id,
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
        })
    return hits_out


def v2ex_fetch(node: str | None, args: argparse.Namespace) -> list[dict]:
    try:
        if node:
            topics = http_get_json(
                f"{V2EX_NODE}?{urllib.parse.urlencode({'node_name': node, 'page': 1})}"
            )
        else:
            topics = http_get_json(V2EX_HOT)
    except Exception as e:
        print(f"err v2ex {node or 'hot'}: {e}", file=sys.stderr)
        return []

    if not isinstance(topics, list):
        topics = []

    hits_out: list[dict] = []
    for t in topics[: args.limit]:
        replies = int(t.get("replies") or 0)
        if replies < args.min_comments:
            continue
        node_title = t.get("node", {}).get("title") if isinstance(t.get("node"), dict) else node
        hits_out.append({
            "platform": "v2ex",
            "community": node_title or node or "hot",
            "id": t.get("id"),
            "title": t.get("title", ""),
            "url": f"https://www.v2ex.com/t/{t.get('id')}",
            "comments": replies,
            "score": replies,
            "member": t.get("member", {}).get("username") if isinstance(t.get("member"), dict) else None,
            "created": t.get("created"),
            "data_source": "v2ex.com/api",
            "top_comment_phrases": ["", "", ""],
        })
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

    payload = {"command": "plan-communities", "as_of": utc_now().isoformat(), "plan": plan}
    _write_out(payload, args.out)
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
        "as_of": utc_now().isoformat(),
        "window_hours": args.hours,
        "filters": {"min_score": args.min_score, "min_comments": args.min_comments},
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
        "platform": "browser",
        "as_of": utc_now().isoformat(),
        "result": result,
    }
    _write_out(payload, args.out)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline: plan → discover → extract → HN/V2EX → combined JSON for Agent Step C."""
    # Plan communities
    plan_args = argparse.Namespace(
        target=args.target,
        subs=args.subs,
        hn_query=args.hn_query,
        v2ex_node=args.v2ex_node,
        plan_json=args.plan_json,
        out=None,
    )
    if args.subs:
        plan = infer_communities(args.target)
        plan["reddit_subs"] = [s.strip() for s in args.subs.split(",") if s.strip()]
    elif args.plan_json:
        with open(args.plan_json, encoding="utf-8") as f:
            plan = json.load(f)
    else:
        plan = infer_communities(args.target)

    if args.hn_query:
        plan["hn_queries"] = [q.strip() for q in args.hn_query.split("|") if q.strip()]
    if args.v2ex_node:
        plan["v2ex_nodes"] = [n.strip() for n in args.v2ex_node.split(",") if n.strip()]

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

    # Step B: extract Reddit
    reddit_posts: list[dict] = []
    for i, sub in enumerate(extract_targets):
        if i:
            time.sleep(args.delay)
        reddit_posts.extend(extract_from_sub(sub, args, after))

    # Step B: HN supplement (English / SaaS / dev targets)
    hn_posts: list[dict] = []
    if not args.no_hn and plan.get("hn_queries"):
        for q in plan["hn_queries"][:2]:
            time.sleep(args.delay)
            hn_posts.extend(hn_search(q, args, after))

    # Step B: V2EX supplement (Chinese targets)
    v2ex_posts: list[dict] = []
    if not args.no_v2ex and plan.get("v2ex_nodes"):
        for node in plan["v2ex_nodes"][:3]:
            time.sleep(args.delay)
            v2ex_posts.extend(v2ex_fetch(node, args))

    # Browser fallback if too few posts
    browser_notes: list[dict] = []
    total = len(reddit_posts) + len(hn_posts) + len(v2ex_posts)
    if total < args.min_total_posts and args.browser_fallback:
        for url in plan.get("browser_fallback_urls", [])[:2]:
            time.sleep(2)
            br = browser_read_url(url)
            browser_notes.append(br)
            print(f"browser fallback: {url} ok={br.get('ok')}", file=sys.stderr)

    all_posts = reddit_posts + hn_posts + v2ex_posts
    all_posts.sort(key=lambda x: x.get("comments", 0) * 2 + x.get("score", 0), reverse=True)

    payload = {
        "command": "run",
        "version": "2.0",
        "as_of": utc_now().isoformat(),
        "target": args.target,
        "plan": plan,
        "window_hours": args.hours,
        "filters": {"min_score": args.min_score, "min_comments": args.min_comments},
        "step_a": {
            "qualified_communities": qualified,
            "all_communities": all_subs,
        },
        "step_b": {
            "posts_by_platform": {
                "reddit": len(reddit_posts),
                "hackernews": len(hn_posts),
                "v2ex": len(v2ex_posts),
            },
            "posts": all_posts,
            "browser_fallback": browser_notes if browser_notes else None,
        },
        "step_c_hint": "Agent: cluster pains → 5 micro-products → best pick → 10 hooks. Map each idea to ≥1 post.",
        "total_posts": len(all_posts),
    }
    _write_out(payload, args.out)
    return 0


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
    pl.add_argument("--out", default=None)
    pl.set_defaults(func=cmd_plan)

    r = sub.add_parser("run", help="Full pipeline: plan + discover + extract + supplements")
    r.add_argument("--target", required=True)
    r.add_argument("--subs", default=None)
    r.add_argument("--hn-query", default=None)
    r.add_argument("--v2ex-node", default=None)
    r.add_argument("--plan-json", default=None)
    r.add_argument("--max-subs", type=int, default=10)
    r.add_argument("--min-total-posts", type=int, default=5,
                   help="Trigger browser fallback if fewer posts found")
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
    h.add_argument("--out", default=None)
    h.set_defaults(func=cmd_hn_search)

    v = sub.add_parser("v2ex-hot", help="Fetch V2EX hot or node topics (login-free)")
    v.add_argument("--node", default=None)
    v.add_argument("--limit", type=int, default=30)
    v.add_argument("--min-comments", type=int, default=20)
    v.add_argument("--out", default=None)
    v.set_defaults(func=cmd_v2ex_hot)

    b = sub.add_parser("browser-read", help="Read public page via Jina Reader (login-free)")
    b.add_argument("--url", required=True)
    b.add_argument("--max-chars", type=int, default=8000)
    b.add_argument("--out", default=None)
    b.set_defaults(func=cmd_browser_read)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())