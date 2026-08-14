from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..provenance import ResultProvenance
from ..workbook import GoldenWorkbook
from .auth import AccessCodeSessionService
from .dto import ForecastAdjustmentMetadataResponse, ForecastInputMetadataResponse
from .errors import ApiErrorCode, BffError


ADJUSTMENT_KEY_PATTERN = re.compile(r"^(manufacturing|sga):([0-9]{3})$")


class ForecastInputMetadataService:
    """Admin-only metadata adapter over the trusted mapping and Base Workbook.

    Workbook rows remain an internal Engine detail.  The browser receives an
    opaque, mapping-version-scoped ordinal key and sends it back unchanged;
    this service resolves that key to the existing canonical Engine row.
    """

    def __init__(
        self,
        sessions: AccessCodeSessionService,
        repository: Any,
        mapping: Mapping[str, Any],
        provenance: ResultProvenance,
    ) -> None:
        self._sessions = sessions
        self._repository = repository
        self._mapping = dict(mapping)
        self._provenance = provenance

    def get(self, session_id: str, base_model_id: str) -> ForecastInputMetadataResponse:
        self._sessions.require_admin(session_id)
        model = self._require_model(base_model_id)
        try:
            path = Path(self._repository.path(model.id))
            expected_sha = str(model.workbook_sha256 or "")
            if not expected_sha or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
                raise ValueError("Base Workbook SHA-256 mismatch")
            workbook = GoldenWorkbook(path)
            manufacturing = tuple(
                ForecastAdjustmentMetadataResponse(
                    adjustment_key=self._key("manufacturing", index),
                    display_name=self._label(workbook, int(row)),
                    category="manufacturing",
                    section=None,
                )
                for index, row in enumerate(self._rows("manufacturing"))
            )
            sga = tuple(
                ForecastAdjustmentMetadataResponse(
                    adjustment_key=self._key("sga", index),
                    display_name=self._label(workbook, int(row)),
                    category="sga",
                    section=self._sga_section(workbook, int(row)),
                )
                for index, row in enumerate(self._rows("sga"))
            )
            return ForecastInputMetadataResponse(
                base_model_id=str(uuid.UUID(str(model.id))),
                manufacturing=manufacturing,
                sga=sga,
            )
        except BffError:
            raise
        except Exception as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Forecast input metadata could not be verified",
            ) from exc

    def resolve_adjustment_keys(
        self,
        session_id: str,
        base_model_id: str,
        category: str,
        keys: Sequence[str],
    ) -> Mapping[str, int]:
        self._sessions.require_admin(session_id)
        self._require_model(base_model_id)
        rows = self._rows(category)
        resolved: dict[str, int] = {}
        for key in keys:
            match = ADJUSTMENT_KEY_PATTERN.fullmatch(str(key))
            if match is None or match.group(1) != category:
                raise BffError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "Forecast adjustment key is invalid",
                    field_errors={"adjustment_key": "unsupported adjustment key"},
                )
            index = int(match.group(2))
            if index >= len(rows):
                raise BffError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "Forecast adjustment key is invalid",
                    field_errors={"adjustment_key": "unsupported adjustment key"},
                )
            resolved[str(key)] = int(rows[index])
        return resolved

    def _require_model(self, base_model_id: str) -> Any:
        try:
            normalized = str(uuid.UUID(str(base_model_id)))
            model = self._repository.get(normalized)
        except Exception as exc:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base Model is not available") from exc
        if (
            not bool(model.is_published)
            or str(model.mapping_status) != "published"
            or str(model.mapping_version) != self._provenance.mapping_version
            or str(model.mapping_hash) != self._provenance.mapping_hash
        ):
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base Model is not available")
        return model

    def _rows(self, category: str) -> tuple[int, ...]:
        field = {
            "manufacturing": "manufacturing_input_rows",
            "sga": "sga_input_rows",
        }.get(category)
        if field is None:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Forecast adjustment category is invalid",
            )
        values = self._mapping.get(field)
        if not isinstance(values, list) or not values:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Forecast adjustment metadata is unavailable",
            )
        return tuple(int(value) for value in values)

    @staticmethod
    def _key(category: str, index: int) -> str:
        if index > 999:
            raise ValueError("too many Forecast adjustment rows")
        return f"{category}:{index:03d}"

    @staticmethod
    def _label(workbook: GoldenWorkbook, row: int) -> str:
        for column in ("D", "C", "B", "A"):
            value = str(workbook.raw_value(f"{column}{row}") or "").strip()
            if value:
                if len(value) > 160 or any(ord(character) < 32 for character in value):
                    raise ValueError("unsafe Forecast adjustment label")
                return value
        raise ValueError("Forecast adjustment label is missing")

    @staticmethod
    def _sga_section(workbook: GoldenWorkbook, row: int) -> str:
        for candidate in range(row, max(0, row - 200), -1):
            value = str(workbook.raw_value(f"B{candidate}") or "").strip()
            if value == "판매비":
                return "selling"
            if value == "일반관리비":
                return "general_admin"
        return "sga"
