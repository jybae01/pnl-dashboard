from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from forecast.engine import ForecastResult
from forecast.persistence import LegacyResultPublisher, ModelRepository
from forecast.persistence.local import LocalModelRepositoryAdapter, LocalResultRepositoryAdapter
from forecast.storage import ModelRegistry, ResultStore
from forecast.provenance import ResultProvenance


def workbook_bytes(path: Path) -> bytes:
    workbook = Workbook()
    workbook.active.title = "Data"
    workbook.save(path)
    return path.read_bytes()


class Phase1StorageCompatibilityTests(unittest.TestCase):
    def test_legacy_confirmed_model_is_exposed_as_published(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ModelRegistry(directory)
            registry.index.write_text(json.dumps([{
                "id": "legacy",
                "name": "legacy",
                "model_type": "actual",
                "year": 2026,
                "start_month": 1,
                "end_month": 12,
                "created_date": "2026-01-01",
                "version": "V1",
                "confirmed": True,
                "file_name": "legacy.xlsx",
                "uploaded_at": "2026-01-01T00:00:00+09:00",
            }]), encoding="utf-8")

            model = registry.list()[0]

        self.assertTrue(model.confirmed)
        self.assertTrue(model.is_published)
        self.assertFalse(model.is_default)
        self.assertEqual(model.mapping_status, "published")

    def test_new_publication_flags_keep_confirmed_and_single_default_in_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = workbook_bytes(root / "source.xlsx")
            registry = ModelRegistry(root / "registry")
            first = registry.add(
                content,
                name="first",
                model_type="plan",
                year=2026,
                confirmed=False,
                is_published=True,
                is_default=True,
            )
            second = registry.add(
                content,
                name="second",
                model_type="forecast",
                year=2026,
                confirmed=True,
            )
            registry.set_publication(second.id, is_published=True, is_default=True)
            models = {model.id: model for model in registry.list()}

        self.assertTrue(first.confirmed)
        self.assertTrue(first.is_published)
        self.assertFalse(models[first.id].is_default)
        self.assertTrue(models[second.id].is_default)

    def test_existing_registry_is_reached_through_repository_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            provenance = ResultProvenance("1.1.0", "mapping-v1", "d" * 64, "1")
            adapter = LocalModelRepositoryAdapter(ModelRegistry(directory), provenance)
            self.assertIsInstance(adapter, ModelRepository)
            self.assertEqual(adapter.list(), [])

    def test_result_store_persists_required_provenance_without_decimal_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "result.xlsx"
            workbook_bytes(workbook)
            result = ForecastResult(
                month=7,
                revenue=10.5,
                cogs=4.5,
                gross_profit=6.0,
                sga=1.0,
                operating_profit=5.0,
                operating_margin=0.5,
                detail={},
                validations=[],
                input_log=[],
                workbook_path=str(workbook),
            )
            adapter = LocalResultRepositoryAdapter(ResultStore(root / "store"))
            self.assertIsInstance(adapter, LegacyResultPublisher)
            adapter.confirm(
                result,
                engine_version="1.1.0",
                mapping_version="analysis-v1.0.0",
                mapping_hash="a" * 64,
                result_schema_version="1",
                job_id="job-1",
                model_id="model-1",
            )
            saved = adapter.load()

        self.assertEqual(saved["engine_version"], "1.1.0")
        self.assertEqual(saved["mapping_version"], "analysis-v1.0.0")
        self.assertEqual(saved["mapping_hash"], "a" * 64)
        self.assertEqual(saved["result_schema_version"], "1")
        self.assertIsInstance(saved["revenue"], float)


if __name__ == "__main__":
    unittest.main()
