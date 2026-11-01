import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laga.compliance import LawCache, ReviewUnavailable, SOURCES, review


class ComplianceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.time = datetime(2026, 10, 31, tzinfo=timezone.utc)
        self.calls = []
        def fetch(url):
            self.calls.append(url)
            return "Official source " + url
        self.cache = LawCache(str(Path(self.temp.name) / "laws.db"), fetch, lambda: self.time)

    def assess(self, **kwargs):
        return review(self.cache, state="NC", property_states=["NC"], text="Lease terms",
                      as_of="2026-10-31", kind="policy", scope_key="property:1", **kwargs)

    def test_cache_shared_across_repeated_upload_and_answer_reviews(self):
        first = self.assess()
        second = review(self.cache, state="NC", property_states=["NC"], text="Final answer",
                        as_of="2026-10-31", kind="answer", scope_key="lease:1")
        self.assertEqual(len(self.calls), len(SOURCES))
        self.assertEqual(first["lawRevision"], second["lawRevision"])
        self.assertNotEqual(first["contentHash"], second["contentHash"])
        self.assertEqual(first["status"], "pending")

    def test_expiration_refresh_and_failure_blocks_stale_copy(self):
        self.cache.get("NC")
        self.time += timedelta(days=2)
        def offline(url):
            raise OSError("offline")
        self.cache.fetcher = offline
        self.assertEqual(self.assess()["status"], "unavailable")

    def test_unsupported_and_mismatched_state(self):
        with self.assertRaises(ReviewUnavailable):
            self.cache.get("TX")
        with self.assertRaises(ValueError):
            review(self.cache, state="NC", property_states=["TX"], text="Rules",
                   as_of="2026-10-31", kind="policy", scope_key="property:1")

    def test_reviewer_requires_complete_coverage_and_official_citations(self):
        self.assertEqual(self.assess(reviewer=lambda **_: {"status": "passed"})["status"], "pending")
        assessment = {"status": "passed", "coverageComplete": True,
                      "citations": [{"url": SOURCES[0], "section": "42-42"}], "findings": []}
        self.assertEqual(self.assess(reviewer=lambda **_: assessment)["status"], "passed")
        assessment["citations"][0]["url"] = "https://example.com"
        self.assertEqual(self.assess(reviewer=lambda **_: assessment)["status"], "pending")

    def test_conflict_or_reviewer_failure_never_passes(self):
        self.assertEqual(self.assess(reviewer=lambda **_: {"status": "conflict", "findings": []})["status"], "conflict")
        def broken(**kwargs):
            raise RuntimeError("review failed")
        self.assertEqual(self.assess(reviewer=broken)["status"], "unavailable")


    def test_review_expiring_during_assessment_is_withheld(self):
        def slow_review(**kwargs):
            self.time += timedelta(days=2)
            return {"status": "passed", "coverageComplete": True,
                    "citations": [{"url": SOURCES[0], "section": "42-42"}]}
        self.assertEqual(self.assess(reviewer=slow_review)["status"], "unavailable")

    def test_invalid_reference_date_rejected(self):
        for value in ["2026-02-30", "20261031"]:
            with self.assertRaises(ValueError):
                review(self.cache, state="NC", property_states=["NC"], text="Rules",
                       as_of=value, kind="policy", scope_key="property:1")


if __name__ == "__main__":
    unittest.main()
