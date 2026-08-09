from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forecast.mapping_config import LocalMappingConfigRepository, MappingStatus, MappingVersion
from forecast.provenance import mapping_hash


ROOT = Path(__file__).resolve().parents[1]


class Phase1MappingConfigTests(unittest.TestCase):
    def test_mapping_hash_matches_checked_in_registry(self):
        registry = json.loads((ROOT / "config" / "mapping_registry.json").read_text(encoding="utf-8"))
        active = next(item for item in registry["versions"] if item["version"] == registry["active_version"])

        self.assertEqual(mapping_hash(ROOT / "config" / active["file"]), active["content_hash"])
        self.assertEqual(active["status"], "published")
        self.assertTrue(active["is_default"])

    def test_only_draft_validated_published_transition_is_allowed(self):
        draft = MappingVersion.draft("model_mapping", "2", {"row": 1})
        with self.assertRaisesRegex(ValueError, "invalid mapping transition"):
            draft.transition(MappingStatus.PUBLISHED)

        validated = draft.transition(MappingStatus.VALIDATED)
        published = validated.transition(MappingStatus.PUBLISHED, is_default=True)

        self.assertEqual(published.status, MappingStatus.PUBLISHED)
        self.assertTrue(published.is_default)
        with self.assertRaisesRegex(ValueError, "invalid mapping transition"):
            published.transition(MappingStatus.VALIDATED)

    def test_local_repository_mirrors_versioned_publish_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LocalMappingConfigRepository(Path(directory) / "mappings.json")
            repository.create_draft("model_mapping", "2", {"row": 1})
            repository.validate("model_mapping", "2")
            published = repository.publish("model_mapping", "2")
            loaded = repository.get_published("model_mapping")

        self.assertEqual(published.content_hash, mapping_hash({"row": 1}))
        self.assertEqual(loaded.version, "2")
        self.assertTrue(loaded.is_default)


if __name__ == "__main__":
    unittest.main()
