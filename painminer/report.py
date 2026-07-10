"""Deterministic Markdown report renderer for evidence-preserving research output."""

from __future__ import annotations

from typing import Any

from painminer.analysis import analyze_research
from painminer.research import parse_target


def _value(value: Any) -> str:
    if value is None or value == "" or value == []:
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _link(label: str, url: Any) -> str:
    return f"[{label}]({url})" if url else label


def _analysis_for(payload: dict[str, Any]) -> dict[str, Any]:
    existing = payload.get("analysis")
    if (
        isinstance(existing, dict)
        and isinstance(existing.get("pain_clusters"), list)
        and isinstance(existing.get("evidence_verdict"), dict)
    ):
        return existing
    if isinstance(payload.get("pain_clusters"), list):
        return payload
    return analyze_research(payload)


def render_report(payload: dict[str, Any]) -> str:
    """Render the complete nine-section report without inventing evidence or conclusions."""
    analysis = _analysis_for(payload)
    target = str(payload.get("target") or analysis.get("target") or "unknown")
    target_profile = analysis.get("target_profile") or payload.get("target_profile") or parse_target(target)
    scope = payload.get("research_scope") if isinstance(payload.get("research_scope"), dict) else {}
    posts = analysis.get("posts") if isinstance(analysis.get("posts"), list) else payload.get("step_b", {}).get("posts", [])
    evidence_posts = [post for post in posts if post.get("target_relevance") != "low"]
    low_relevance_count = len(posts) - len(evidence_posts)
    step_a = payload.get("step_a") if isinstance(payload.get("step_a"), dict) else {}
    communities = step_a.get("community_profiles") or step_a.get("qualified_communities", [])
    filters = payload.get("filters", {})
    verdict = analysis.get("evidence_verdict") if isinstance(analysis.get("evidence_verdict"), dict) else {}
    source_health = payload.get("source_health") if isinstance(payload.get("source_health"), dict) else {}
    lines = [
        f"# 痛点研究报告：{target}", "",
        "## 1. 研究范围", "",
        f"- 目标用户：{_value(target_profile.get('raw'))}",
        f"- 角色：{_value(target_profile.get('roles'))}",
        f"- 任务线索：{_value(target_profile.get('jobs'))}",
        f"- 语言：{_value(target_profile.get('languages'))}",
        f"- 时间窗口：过去 {_value(scope.get('time_window_hours') or payload.get('window_hours'))} 小时",
        f"- 平台：{_value(scope.get('platforms'))}",
        f"- 筛选：赞 ≥ {_value(filters.get('min_score'))}；评论 ≥ {_value(filters.get('min_comments'))}",
        f"- 研究判定：{_value(verdict.get('status'))}（主证据 {_value(verdict.get('primary_evidence_count'))} / 最低 {_value(verdict.get('minimum_primary_evidence'))}）",
        "",
    "## 2. 社区地图", "",
        "| 社区 | 规模层级 | 活跃度 | 相关度 | 研究适配 | 信号质量 | 偏差风险 |",
        "|---|---|---|---|---|---|---|",
    ]
    for community in communities:
        assessment = community.get("research_assessment", {})
        lines.append(
            "| {community} | {tier} | {activity} | {relevance} | {fit} | {quality} | {risks} |".format(
                community=_value(community.get("community")), tier=_value(community.get("member_tier")),
                activity=_value(assessment.get("activity") or community.get("posts_in_window")),
                relevance=_value(assessment.get("relevance")), fit=_value(assessment.get("research_fit")),
                quality=_value(assessment.get("signal_quality")), risks=_value(community.get("risk_flags")),
            )
        )
    if not communities:
        lines.append("| unknown | unknown | unknown | unknown | unknown | unknown | 未提供社区发现结果 |")

    lines += ["", "## 3. 高价值证据", "", "| 意图 | 社区 | 用户原话摘要 | 当前方案 | 想要结果 | 证据类型/风险 |", "|---|---|---|---|---|---|"]
    for post in evidence_posts:
        signal = post.get("commercial_signals", {})
        summary = post.get("pain_statement") or post.get("selftext") or post.get("story_text") or post.get("title")
        title = _link(str(post.get("title") or "来源帖"), post.get("url"))
        lines.append(
            f"| {_value(post.get('post_intent'))} | {_value(post.get('community'))} | {title}: {_value(summary)} | "
            f"{_value(signal.get('current_solution'))} | {_value(post.get('desired_outcome'))} | "
            f"{_value(post.get('evidence_type'))} / {_value(post.get('risk_flags'))} |"
        )
    if not evidence_posts:
        lines.append("| unknown | unknown | 未采集到符合条件的帖子 | unknown | unknown | unknown |")
    if low_relevance_count:
        lines.append(f"\n已排除 {low_relevance_count} 条与目标用户低相关的帖子；它们保留在 JSON `analysis.posts` 中供审计，但不作为研究证据。")

    lines += ["", "## 4. 痛点结构", ""]
    for cluster in analysis.get("pain_clusters", []):
        structure = cluster.get("pain_structure", {})
        lines += [
            f"### {cluster.get('pain_id')}: {_value(cluster.get('label'))}",
            f"- 结构：{_value(structure.get('domain'))} → {_value(structure.get('task_scenario'))} → {_value(structure.get('specific_obstacle'))}",
            f"- 信号面板：{_value(cluster.get('signals'))}",
        ]
    if not analysis.get("pain_clusters"):
        lines.append("未形成痛点簇；请扩大样本或放宽筛选条件。")

    lines += ["", "## 5. 跨社区共识与分歧", ""]
    for comparison in analysis.get("community_comparisons", []):
        lines.append(f"- {_value(comparison.get('shared_pain'))}：{_value(comparison.get('community_differences'))}")
        lines.append(f"  - 可能根因：{_value(comparison.get('possible_root_problem'))}")
    if not analysis.get("community_comparisons"):
        lines.append(f"暂无跨社区共识（{_value(analysis.get('community_comparisons_status'))}）；单一社区观察不得外推为普遍需求。")

    lines += ["", "## 6. 商业信号", ""]
    for cluster in analysis.get("pain_clusters", []):
        signals = cluster.get("signals", {})
        lines.append(
            f"- {_value(cluster.get('label'))}：付费意愿 {_value(signals.get('purchase_intent'))}；"
            f"临时方案成本 {_value(signals.get('workaround_cost'))}；现有方案不满 {_value(signals.get('existing_solution_dissatisfaction'))}；"
            f"已观察替代方案 {_value(cluster.get('existing_alternatives'))}。"
        )
    if not analysis.get("pain_clusters"):
        lines.append("暂无可报告的商业信号。")

    lines += ["", "## 7. 候选产品方向", ""]
    for card in analysis.get("opportunities", []):
        lines += [
            f"### {_value(card.get('opportunity'))}",
            f"- 要完成的任务：{_value(card.get('job_to_be_done'))}",
            f"- 支持证据：{_value(card.get('supporting_evidence'))}",
            f"- 反证/边界：{_value(card.get('counter_evidence'))}",
            f"- 已有替代方案：{_value(card.get('existing_alternatives'))}",
            f"- 未解决问题：{_value(card.get('unresolved_questions'))}",
        ]
    if not analysis.get("opportunities"):
        lines.append("暂无候选方向；不应在证据不足时生成产品结论。")

    lines += ["", "## 8. 推荐验证方案", ""]
    for card in analysis.get("opportunities", []):
        validation = card.get("recommended_validation", {})
        lines.append(
            f"- {_value(card.get('opportunity'))}：{_value(validation.get('method'))}；"
            f"行动：{_value(validation.get('action'))}；成功：{_value(validation.get('success_signal'))}；"
            f"放弃：{_value(validation.get('abandon_signal'))}。"
        )
    if not analysis.get("opportunities"):
        lines.append("暂无验证动作。")

    lines += ["", "## 9. 证据附录", ""]
    for post in evidence_posts:
        lines.append(
            f"- {_link(str(post.get('title') or '来源帖'), post.get('url'))}"
            f"（{_value(post.get('platform'))} / {_value(post.get('community'))}；"
            f"来源：{_value(post.get('source_snapshot', {}).get('data_source') or post.get('data_source'))}；"
            f"抓取：{_value(post.get('source_snapshot', {}).get('captured_at'))}）"
        )
    lines += ["", "### 数据限制", ""]
    lines.extend(f"- {item}" for item in analysis.get("limitations", []))
    lines += ["", "### 数据源健康度", ""]
    if source_health:
        for source, status in source_health.items():
            lines.append(f"- {source}：{_value(status.get('status'))}；{_value(status.get('reason'))}")
    else:
        lines.append("- 未在输入中捕获 `source_health`；不能据此判断任一社区没有讨论。")
    if verdict.get("status") == "INSUFFICIENT_EVIDENCE":
        lines += ["", "### 证据不足：下一步", ""]
        lines.extend(f"- {action}" for action in verdict.get("next_actions", []))
    return "\n".join(lines) + "\n"
