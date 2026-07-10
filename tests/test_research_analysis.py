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
        payload = {
            "target": "SaaS founders",
            "step_b": {"posts": [
                {
                    "platform": "reddit", "community": "r/SaaS", "id": "a", "author": "alice",
                    "title": "I need an alternative because feedback is manual", "selftext": "I use a spreadsheet workaround.",
                    "url": "https://example.test/a", "pain_themes": ["tools/workflow"],
                    "post_intent": "alternative_search", "evidence_type": "primary_evidence",
                    "commercial_signals": {"current_solution": "spreadsheet", "workaround_present": True, "willingness_to_pay": "implicit"},
                },
                {
                    "platform": "reddit", "community": "r/ProductManagement", "id": "b", "author": "bob",
                    "title": "I need an alternative because feedback is manual", "selftext": "Would pay for a tool.",
                    "url": "https://example.test/b?ref=affiliate", "pain_themes": ["tools/workflow"],
                    "post_intent": "purchase_intent", "evidence_type": "primary_evidence",
                    "commercial_signals": {"current_solution": None, "workaround_present": False, "willingness_to_pay": "explicit"},
                },
                {
                    "platform": "reddit", "community": "r/SaaS", "id": "c", "author": "alice",
                    "title": "I need an alternative because feedback is manual", "selftext": "I use a spreadsheet workaround.",
                    "url": "https://example.test/a", "pain_themes": ["tools/workflow"],
                    "post_intent": "alternative_search", "evidence_type": "primary_evidence",
                    "commercial_signals": {"current_solution": "spreadsheet", "workaround_present": True, "willingness_to_pay": "implicit"},
                },
            ]},
        }

        result = pain_miner.analyze_research(payload)

        self.assertEqual(result["schema_version"], "2.2")
        self.assertEqual(result["target_profile"]["raw"], "SaaS founders")
        self.assertIn("founder", result["target_profile"]["roles"])
        self.assertEqual(result["deduplication"]["duplicate_count"], 1)
        self.assertEqual(len(result["pain_clusters"]), 1)
        panel = result["pain_clusters"][0]["signals"]
        self.assertEqual(panel["frequency"], "medium")
        self.assertEqual(panel["cross_community"], "high")
        self.assertEqual(panel["purchase_intent"], "high")
        self.assertEqual(result["opportunities"][0]["recommended_validation"]["method"], "concierge_test")
        self.assertIn("post_contains_affiliate_pattern", result["posts"][1]["risk_flags"])
        self.assertEqual(result["posts"][0]["author_context"]["community_post_count_sample"], 2)

    def test_report_has_all_research_sections_and_cited_evidence(self):
        payload = {
            "target": "SaaS founders",
            "window_hours": 168,
            "filters": {"min_score": 20, "min_comments": 5},
            "step_a": {"qualified_communities": [{
                "platform": "reddit", "community": "r/SaaS", "member_tier": "medium_vertical",
                "posts_in_window": 8, "comments_in_window": 31, "research_assessment": {
                    "relevance": "high", "activity": "medium", "research_fit": "high", "signal_quality": "medium",
                },
            }]},
            "step_b": {"posts": [{
                "platform": "reddit", "community": "r/SaaS", "id": "a", "title": "Feedback is manual",
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


if __name__ == "__main__":
    unittest.main()
