import argparse
import importlib.util
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pain_miner.py"
SPEC = importlib.util.spec_from_file_location("pain_miner", SCRIPT)
pain_miner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = pain_miner
SPEC.loader.exec_module(pain_miner)


class PainMinerTests(unittest.TestCase):
    def test_all_new_and_existing_commands_parse(self):
        parser = pain_miner.build_parser()
        self.assertEqual(parser.parse_args(["run", "--target", "founders"]).command, "run")
        self.assertEqual(parser.parse_args([
            "profile-community", "--platform", "reddit", "--community", "SaaS"
        ]).command, "profile-community")
        self.assertEqual(parser.parse_args([
            "compare-communities", "--input", "result.json", "--topic", "feedback"
        ]).command, "compare-communities")
        self.assertEqual(parser.parse_args([
            "analyze-research", "--input", "result.json"
        ]).command, "analyze-research")
        self.assertEqual(parser.parse_args([
            "render-report", "--input", "result.json"
        ]).command, "render-report")

    def test_intent_and_commercial_signals_are_explicit(self):
        post = pain_miner.enrich_post({
            "title": "Looking for an alternative to Notion under $20",
            "selftext": "My current setup is Notion. I tried spreadsheets but need less manual work and would be willing to pay.",
        })
        self.assertEqual(post["post_intent"], "purchase_intent")
        self.assertTrue(post["commercial_signals"]["budget_mentioned"])
        self.assertEqual(post["commercial_signals"]["willingness_to_pay"], "explicit")
        self.assertTrue(post["commercial_signals"]["alternative_sought"])
        self.assertEqual(post["evidence_type"], "primary_evidence")
        self.assertIsNotNone(post["desired_outcome"])
        self.assertIn("spreadsheets but need less manual work and would be willing to pay", post["failed_attempts"])

    def test_intent_query_plan_and_comment_confirmation_are_structured(self):
        plan = pain_miner.infer_communities("indie developers")
        self.assertIn("alternative_search", plan["intent_queries"])
        post = {"top_comment_phrases": ["Same here, I also use a spreadsheet.", "", ""]}
        pain_miner.annotate_comment_evidence(post)
        self.assertEqual(post["comment_evidence"][0]["evidence_type"], "supporting_evidence")

    def test_promotion_is_not_primary_evidence(self):
        post = pain_miner.enrich_post({"title": "I built a new feedback tool", "selftext": "Check out my app."})
        self.assertEqual(post["post_intent"], "promotion")
        self.assertEqual(post["evidence_type"], "commercially_contaminated")
        self.assertIn("possible_self_promotion", post["risk_flags"])

    def test_small_community_remains_visible_to_discovery(self):
        recent_post = {
            "created_utc": int(pain_miner.utc_now().timestamp()), "subreddit_subscribers": 900,
            "num_comments": 4, "score": 10, "title": "How do I handle manual reporting?",
            "selftext": "", "permalink": "/r/Tiny/comments/1/example/",
        }
        args = argparse.Namespace(hours=72, limit=10, min_members=10000, min_posts=1,
                                  min_comments_total=1, min_active_threads=1)
        with patch.object(pain_miner, "fetch_reddit_posts", return_value=[recent_post]):
            row = pain_miner.discover_sub("Tiny", args)
        self.assertIsNotNone(row)
        self.assertEqual(row["member_tier"], "small_expert")
        self.assertFalse(row["member_threshold_met"])

    def test_profile_uses_public_sample_and_marks_policy_source(self):
        posts = [{
            "subreddit_subscribers": 50000, "num_comments": 4,
            "title": "Founder looking for a workflow alternative", "selftext": "My current setup is a spreadsheet.",
        }]
        with patch.object(pain_miner, "fetch_reddit_posts", return_value=posts), patch.object(
            pain_miner, "browser_read_url", return_value={"ok": True, "text": "No self-promotion. Weekly thread only."}
        ):
            profile = pain_miner.build_community_profile("SaaS")
        self.assertEqual(profile["commercial_content_policy"], "weekly_thread_only")
        self.assertIn("founder", profile["audience_roles"])
        self.assertIn("problem_discovery", profile["research_strengths"])

    def test_compare_keeps_community_difference_and_counter_evidence(self):
        payload = {"step_b": {"posts": [
            {"community": "r/SaaS", "title": "Customer feedback management is manual", "selftext": "I use a spreadsheet workaround.", "url": "https://example/a"},
            {"community": "r/ProductManagement", "title": "Customer feedback management tool is hard", "selftext": "How do I consolidate feedback manually?", "url": "https://example/b"},
        ]}}
        result = pain_miner.compare_communities(payload, "customer feedback management")
        self.assertEqual(result["matched_communities"], 2)
        self.assertEqual(len(result["community_differences"]), 2)
        self.assertIn("tools/workflow", result["shared_pains"])

    def test_run_writes_structured_target_and_research_scope(self):
        args = pain_miner.build_parser().parse_args([
            "run", "--target", "SaaS founders", "--subs", "SaaS", "--no-hn", "--no-v2ex", "--analyze",
        ])
        args.browser_fallback = False
        sample = {"platform": "reddit", "community": "r/SaaS", "id": "1", "title": "Manual workflow is hard",
                  "url": "https://example.test/1", "score": 2, "comments": 3, "pain_themes": ["tools/workflow"],
                  "post_intent": "complaint", "evidence_type": "primary_evidence", "commercial_signals": {}}
        with tempfile.NamedTemporaryFile(suffix=".json") as output, patch.object(
            pain_miner, "discover_sub", return_value=None
        ), patch.object(pain_miner, "extract_from_sub", return_value=[sample]):
            args.out = output.name
            self.assertEqual(pain_miner.cmd_run(args), 0)
            output.seek(0)
            result = json.load(output)
        self.assertEqual(result["target_profile"]["raw"], "SaaS founders")
        self.assertEqual(result["research_scope"]["platforms"], ["reddit"])

    def test_run_accepts_the_enveloped_plan_command_output(self):
        args = pain_miner.build_parser().parse_args([
            "run", "--target", "SaaS founders", "--plan-json", "placeholder.json", "--no-hn", "--no-v2ex",
        ])
        args.browser_fallback = False
        plan_file = tempfile.NamedTemporaryFile(mode="w+", suffix=".json")
        output = tempfile.NamedTemporaryFile(suffix=".json")
        json.dump({"command": "plan-communities", "plan": {"reddit_subs": ["SaaS"], "hn_queries": [], "v2ex_nodes": []}}, plan_file)
        plan_file.flush()
        args.plan_json = plan_file.name
        args.out = output.name
        with patch.object(pain_miner, "discover_sub", return_value=None), patch.object(
            pain_miner, "extract_from_sub", return_value=[]
        ):
            self.assertEqual(pain_miner.cmd_run(args), 0)
        plan_file.close()
        output.close()


if __name__ == "__main__":
    unittest.main()
