import importlib.util
import sys
import unittest
from pathlib import Path

from painminer.report import render_report


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pain_miner.py"
SPEC = importlib.util.spec_from_file_location("pain_miner_analysis", SCRIPT)
pain_miner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = pain_miner
SPEC.loader.exec_module(pain_miner)


class ResearchAnalysisTests(unittest.TestCase):
    def test_analysis_builds_signal_panels_deduplication_and_opportunities(self):
        primary_posts = [
            {
                "platform": "reddit", "community": f"r/SaaS{index}", "id": f"p{index}", "author": f"author{index}",
                "title": f"SaaS founder needs an alternative because feedback is manual {['inbox', 'billing', 'roadmap', 'support', 'interviews'][index - 1]}",
                "selftext": "I use a spreadsheet workaround and would pay for less manual work.",
                "url": f"https://example.test/p{index}", "pain_themes": ["tools/workflow"],
                "post_intent": "alternative_search", "evidence_type": "primary_evidence",
                "commercial_signals": {"current_solution": "spreadsheet", "workaround_present": True, "willingness_to_pay": "implicit"},
            }
            for index in range(1, 6)
        ]
        payload = {
            "target": "SaaS founders",
            "step_b": {"posts": primary_posts + [
                {
                    "platform": "reddit", "community": "r/SaaS", "id": "duplicate", "author": "author1",
                    "title": "SaaS founder needs an alternative because feedback is manual inbox", "selftext": "I use a spreadsheet workaround and would pay for less manual work.",
                    "url": "https://example.test/p1", "pain_themes": ["tools/workflow"],
                    "post_intent": "purchase_intent", "evidence_type": "primary_evidence",
                    "commercial_signals": {"current_solution": "spreadsheet", "workaround_present": True, "willingness_to_pay": "implicit"},
                },
            ]},
        }

        result = pain_miner.analyze_research(payload)

        self.assertEqual(result["schema_version"], "2.3")
        self.assertEqual(result["target_profile"]["raw"], "SaaS founders")
        self.assertIn("founder", result["target_profile"]["roles"])
        self.assertEqual(result["deduplication"]["duplicate_count"], 1)
        self.assertEqual(len(result["pain_clusters"]), 1)
        panel = result["pain_clusters"][0]["signals"]
        self.assertEqual(panel["frequency"], "high")
        self.assertEqual(panel["cross_community"], "high")
        self.assertEqual(panel["purchase_intent"], "medium")
        self.assertEqual(result["evidence_verdict"]["status"], "READY")
        self.assertEqual(result["opportunities"][0]["recommended_validation"]["method"], "concierge_test")
        self.assertEqual(result["posts"][0]["author_context"]["community_post_count_sample"], 1)

    def test_insufficient_or_low_relevance_evidence_cannot_create_opportunities(self):
        result = pain_miner.analyze_research({
            "target": "独立 SaaS 创业者",
            "step_b": {"posts": [{
                "platform": "v2ex", "community": "career", "title": "校长收入和社保", "url": "https://example.test/career",
                "post_intent": "complaint", "evidence_type": "primary_evidence", "pain_themes": ["cost/pricing"],
                "commercial_signals": {},
            }]},
        })
        self.assertEqual(result["posts"][0]["target_relevance"], "low")
        self.assertEqual(result["evidence_verdict"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["opportunities"], [])

    def test_planned_saas_community_is_a_relevance_cue_but_career_noise_is_not(self):
        result = pain_miner.analyze_research({
            "target": "独立 SaaS 创业者",
            "step_b": {"posts": [
                {"platform": "reddit", "community": "r/SaaS", "title": "How should I get my first customers?", "url": "https://example.test/saas", "evidence_type": "primary_evidence", "pain_themes": ["support/community"], "commercial_signals": {}},
                {"platform": "v2ex", "community": "career", "title": "社保和工资", "url": "https://example.test/career", "evidence_type": "primary_evidence", "pain_themes": ["cost/pricing"], "commercial_signals": {}},
            ]},
        })
        self.assertEqual(result["posts"][0]["target_relevance"], "high")
        self.assertEqual(result["posts"][1]["target_relevance"], "low")

    def test_report_has_all_research_sections_and_cited_evidence(self):
        payload = {
            "target": "SaaS founders",
            "window_hours": 168,
            "filters": {"min_score": 20, "min_comments": 5},
            "source_health": {"arctic_shift": {"status": "degraded", "reason": "score_lag_or_thresholds"}},
            "step_a": {"qualified_communities": [{
                "platform": "reddit", "community": "r/SaaS", "member_tier": "medium_vertical",
                "posts_in_window": 8, "comments_in_window": 31, "research_assessment": {
                    "relevance": "high", "activity": "medium", "research_fit": "high", "signal_quality": "medium",
                },
            }]},
            "step_b": {"posts": [{
                "platform": "reddit", "community": "r/SaaS", "id": "a", "title": "SaaS founder feedback is manual",
                "url": "https://example.test/a", "score": 21, "comments": 8, "selftext": "I use a spreadsheet workaround.",
                "pain_themes": ["tools/workflow"], "post_intent": "workaround_share",
                "evidence_type": "primary_evidence", "risk_flags": [],
                "commercial_signals": {"current_solution": "spreadsheet", "workaround_present": True, "willingness_to_pay": "unknown"},
            }]},
        }

        text = render_report(payload)

        for heading in (
            "## 1. 研究范围", "## 2. 社区地图", "## 3. 高价值证据", "## 4. 痛点结构",
            "## 5. 跨社区共识与分歧", "## 6. 商业信号", "## 7. 候选产品方向",
            "## 8. 推荐验证方案", "## 9. 证据附录",
        ):
            self.assertIn(heading, text)
        self.assertIn("https://example.test/a", text)
        self.assertIn("primary_evidence", text)
        self.assertIn("INSUFFICIENT_EVIDENCE", text)
        self.assertIn("数据源健康度", text)
        self.assertNotIn("Step A", text)
        self.assertNotIn("Step B", text)
        self.assertNotIn("Step C", text)


if __name__ == "__main__":
    unittest.main()
