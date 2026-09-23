import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from model_catalogue import (
    CatalogueState, compare_catalogue, discover_catalogue, parse_catalogue,
)


def cache_document(models=None, fetched_at="2026-09-22T12:00:00Z"):
    return {
        "fetched_at": fetched_at,
        "client_version": "0.155.0",
        "models": models or [{
            "slug": "gpt-6-sol", "visibility": "list",
            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}],
            "service_tiers": [{"id": "priority"}],
            "upgrade": {"model": "gpt-6-astra", "retirement_at": None},
        }],
    }


class ModelCatalogueTests(unittest.TestCase):
    def test_exact_visible_model_is_available_and_exposes_allowlisted_fields(self):
        result = parse_catalogue(cache_document(), now=datetime(2026, 9, 22, 13, tzinfo=timezone.utc))
        self.assertEqual(result.state, CatalogueState.COMPLETE)
        self.assertEqual(result.availability("gpt-6-sol").value, "available")
        observation = result.models[0]
        self.assertEqual(observation.efforts, ("high", "low", "medium"))
        self.assertEqual(observation.service_tiers, ("priority",))
        self.assertEqual(observation.upgrade_model, "gpt-6-astra")

    def test_absence_requires_complete_valid_fresh_catalogue(self):
        result = parse_catalogue(cache_document(), now=datetime(2026, 9, 22, 13, tzinfo=timezone.utc))
        self.assertEqual(result.availability("gpt-6-luna").value, "absent")
        self.assertEqual(parse_catalogue({}, now=datetime.now(timezone.utc)).state, CatalogueState.UNAVAILABLE)
        stale = parse_catalogue(cache_document(fetched_at="2026-09-01T00:00:00Z"), now=datetime(2026, 9, 22, 13, tzinfo=timezone.utc))
        self.assertEqual(stale.state, CatalogueState.UNAVAILABLE)

    def test_hidden_model_is_not_available(self):
        doc = cache_document([{"slug": "gpt-6-sol", "visibility": "hide", "supported_reasoning_levels": [], "service_tiers": []}])
        result = parse_catalogue(doc, now=datetime(2026, 9, 22, 13, tzinfo=timezone.utc))
        self.assertEqual(result.availability("gpt-6-sol").value, "hidden_nonselectable")

    def test_malformed_duplicate_oversized_or_excessive_catalogue_is_unavailable(self):
        now = datetime(2026, 9, 22, 13, tzinfo=timezone.utc)
        malformed = parse_catalogue({"fetched_at": "bad", "models": []}, now=now)
        self.assertEqual(malformed.state, CatalogueState.UNAVAILABLE)
        duplicate = cache_document([{"slug": "gpt-6-sol", "visibility": "list"}, {"slug": "gpt-6-sol", "visibility": "list"}])
        self.assertEqual(parse_catalogue(duplicate, now=now).state, CatalogueState.UNAVAILABLE)
        self.assertEqual(parse_catalogue(cache_document(), now=now, encoded_size=4 * 1024 * 1024 + 1).state, CatalogueState.UNAVAILABLE)
        too_many = cache_document([{"slug": f"model-{i}", "visibility": "list"} for i in range(4097)])
        self.assertEqual(parse_catalogue(too_many, now=now).state, CatalogueState.UNAVAILABLE)

    def test_complete_search_is_required_before_absent(self):
        malformed = parse_catalogue({"fetched_at": "2026-09-22T12:00:00Z", "models": "not-a-list"}, now=datetime(2026, 9, 22, 13, tzinfo=timezone.utc))
        self.assertNotEqual(malformed.availability("gpt-6-sol").value, "absent")

    def test_drift_comparison_separates_ids_fields_and_policy_state(self):
        current = parse_catalogue(cache_document([
            {"slug": "gpt-6-sol", "visibility": "list", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}], "service_tiers": [{"id": "priority"}]},
            {"slug": "gpt-6-astra", "visibility": "list", "supported_reasoning_levels": [{"effort": "medium"}], "service_tiers": [{"id": "priority"}]},
        ]), now=datetime(2026, 9, 22, 13, tzinfo=timezone.utc))
        baseline = {
            "schema_version": 1, "revision": "baseline-test", "reviewed_at": "2026-09-22T12:00:00Z",
            "models": [{"id": "gpt-6-sol", "visibility": "list", "efforts": ["medium"], "service_tiers": ["priority"], "upgrade_model": None, "retirement_at": None}],
        }
        report = compare_catalogue(current, baseline)
        self.assertEqual(report.status, "MODEL CATALOGUE CHANGED")
        self.assertIn("gpt-6-astra", report.added_ids)
        self.assertEqual(report.effort_changes[0]["id"], "gpt-6-sol")

    def test_file_discovery_is_bounded_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models_cache.json"
            path.write_text(json.dumps(cache_document()), encoding="utf-8")
            before = path.read_bytes()
            result = discover_catalogue(path, now=datetime(2026, 9, 22, 13, tzinfo=timezone.utc))
            self.assertEqual(result.state, CatalogueState.COMPLETE)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
