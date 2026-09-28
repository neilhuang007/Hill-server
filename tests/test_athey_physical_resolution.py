"""A failed source audit requires its explicit, intact cap resolution."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_hill_athey_dining_connections import audit, verified_physical_resolution
from campus_study_io import digest


class PhysicalResolutionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.study, self.campus = self.root / "study", self.root / "campus"
        self.study.mkdir()
        self.campus.mkdir()
        self.write(self.study / "profile.json", {})
        (self.study / "sample-blocks.npz").write_bytes(b"not decoded before the acceptance gate")
        self.sha = digest(self.study / "sample-blocks.npz")
        self.write(self.study / "manifest.json", {"profile": {"sha256": digest(self.study / "profile.json")}})
        self.write(self.study / "native-review.json", {"status": "accepted_for_bounded_integration", "archive_sha256": self.sha})
        self.write(self.study / "physical-source-audit.json", {"passed": False, "archive_sha256": self.sha})
        self.write(self.campus / "manifest.json", {"blocks_per_metre": 2, "vertical_offset_m": -25,
            "components": [{"study": str(self.study), "archive_sha256": self.sha}]})

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_default_still_rejects_raw_failed_source(self):
        with self.assertRaisesRegex(ValueError, "provide its exact separately resolved"):
            audit(self.campus, self.study)

    def test_resolution_for_other_archive_rejected(self):
        path = self.root / "resolution.json"
        self.write(path, {"format": "hill-athey-physical-source-cap-resolution-v1", "archive_sha256": "wrong", "passed": True, "checks": {str(i): True for i in range(12)}})
        with self.assertRaisesRegex(ValueError, "Invalid source physical"):
            verified_physical_resolution(self.study, self.sha, path)

    def test_modified_raw_input_rejected(self):
        path = self.root / "resolution.json"
        self.write(path, {"format": "hill-athey-physical-source-cap-resolution-v1", "archive_sha256": self.sha,
                         "passed": True, "checks": {str(i): True for i in range(12)},
                         "raw_physical_source_audit": {"sha256": "not-the-current-raw-report"}})
        with self.assertRaisesRegex(ValueError, "Physical resolution input changed"):
            verified_physical_resolution(self.study, self.sha, path)


if __name__ == "__main__":
    unittest.main()
