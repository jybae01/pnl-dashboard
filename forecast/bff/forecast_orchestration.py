from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ..engine import (
    CostAdjustment,
    ForecastEngine,
    ForecastInput,
    SalesInput,
    V11_IX_FREIGHT_RATE,
    V11_TARIFF_ELIGIBLE_RATIO,
    V11_TARIFF_RATE,
    V11_UF_MBR_FREIGHT_RATE,
)
from ..merchandise_cogs import (
    MerchandiseSourceValidationError,
    NewBusinessGoodsCogsSelection,
    NewBusinessGoodsCogsValidationError,
    normalize_new_business_goods_cogs,
)
from ..provenance import ResultProvenance, canonical_json_bytes, mapping_hash
from ..sales_contract import (
    FORECAST_SALES_CONTRACT_VERSION,
    LC_MERCHANDISE_CODE,
    LC_SALES_MODE_EXPLICIT,
    LC_SALES_MODE_LEGACY_PRODUCT_ONLY,
)
from ..workbook import extract_period_types, infer_workbook_year
from .auth import AccessCodeSessionService
from .errors import ApiErrorCode, BffError
from ..temp_artifacts import temp_artifact_policy

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_FORECAST_WORKBOOK_BYTES = 50 * 1024 * 1024
V1_FORECAST_SYNC_MAX_MONTHS = 6


@dataclass(frozen=True)
class ForecastSalesInput:
    product_code: str
    quantity: float
    amount: float


@dataclass(frozen=True)
class ForecastQuantityInput:
    product_code: str
    quantity: float


@dataclass(frozen=True)
class ForecastAdjustmentInput:
    row: int
    amount: float
    reason: str = ""


@dataclass(frozen=True)
class ForecastMonthInput:
    month: int
    sales: tuple[ForecastSalesInput, ...]
    production: tuple[ForecastQuantityInput, ...]
    mcm: tuple[ForecastQuantityInput, ...] = ()
    manufacturing_adjustments: tuple[ForecastAdjustmentInput, ...] = ()
    sga_adjustments: tuple[ForecastAdjustmentInput, ...] = ()
    disposal_adjustment: float = 0
    disposal_reason: str = ""
    obsolescence_adjustment: float = 0
    obsolescence_reason: str = ""
    new_business_goods_cogs_mode: str | None = None
    new_business_goods_cogs: float | None = None
    new_business_goods_cogs_reason: str = ""
    new_business_goods_cogs_legacy_normalized: bool = False
    uf_mbr_cogs_rate: float = 0.85
    ix_cogs_rate: float = 0.85
    uf_mbr_transport_rate: float = V11_UF_MBR_FREIGHT_RATE
    ix_transport_rate: float = V11_IX_FREIGHT_RATE
    ix_pack_liters: float = 25
    ix_pack_cost: float = 380
    plan_na_sa_sales: float = 0
    na_sa_sales: float = 0
    tariff_applicable_rate: float = V11_TARIFF_ELIGIBLE_RATIO
    tariff_rate: float = V11_TARIFF_RATE
    raw_material_basis: str = "model"
    raw_material_direct: float | None = None
    raw_material_adjustment: float = 0
    raw_material_reason: str = ""
    refund_rate: float = 0.013
    sales_contract_version: str = FORECAST_SALES_CONTRACT_VERSION
    lc_sales_mode: str = LC_SALES_MODE_LEGACY_PRODUCT_ONLY


@dataclass(frozen=True)
class ForecastGenerateRequest:
    base_model_id: str
    name: str
    model_year: int
    version: str
    start_month: int
    end_month: int
    months: tuple[ForecastMonthInput, ...]
    idempotency_key: str


@dataclass(frozen=True)
class ForecastGenerateResponse:
    generation_id: str
    model_id: str
    display_name: str
    model_year: int
    start_month: int
    end_month: int
    is_published: bool
    is_default: bool
    workbook_sha256: str
    idempotency_replayed: bool
    execution_mode: str = "SYNCHRONOUS"
    dto_version: str = "1"


@dataclass(frozen=True)
class ForecastReservation:
    generation_id: str
    model_id: str
    status: str
    lease_token: str | None
    replayed: bool
    base_bucket: str
    base_path: str
    base_sha256: str


class ForecastGateway(Protocol):
    def reserve(self, *, actor: str, request: ForecastGenerateRequest,
                payload: Mapping[str, Any], fingerprint: str,
                provenance: ResultProvenance) -> ForecastReservation: ...
    def download_base(self, reservation: ForecastReservation) -> bytes: ...
    def upload_generated(self, model_id: str, path: Path, sha256: str) -> None: ...
    def verify_generated(self, model_id: str, sha256: str) -> None: ...
    def finalize(self, reservation: ForecastReservation, *, sha256: str, name: str,
                 model_year: int, version: str, file_name: str,
                 period_types: Mapping[str, str], provenance: ResultProvenance) -> Mapping[str, Any]: ...
    def remove_generated(self, model_id: str) -> None: ...
    def record_failure(self, reservation: ForecastReservation, *, cleanup_succeeded: bool,
                       error_code: str) -> None: ...
    def get_model(self, model_id: str) -> Mapping[str, Any] | None: ...
    def acquire_execution_permit(self, operation_id: str) -> str: ...
    def renew_execution_permit(self, operation_id: str, lease_token: str) -> None: ...
    def release_execution_permit(self, operation_id: str, lease_token: str) -> None: ...


class ForecastFinalizeUncertainError(RuntimeError):
    """The DB may have committed even though the RPC response was lost."""


class ForecastGenerationService:
    """Admin-only orchestration around the existing deterministic ForecastEngine."""

    def __init__(self, sessions: AccessCodeSessionService, gateway: ForecastGateway,
                 provenance: ResultProvenance, mapping_path: str | Path,
                 mapping: Mapping[str, Any], *, max_execution_seconds: int = 900,
                 max_sync_months: int = V1_FORECAST_SYNC_MAX_MONTHS,
                 merchandise_mapping_path: str | Path | None = None,
                 merchandise_mapping: Mapping[str, Any] | None = None) -> None:
        self._sessions = sessions
        self._gateway = gateway
        self._provenance = provenance
        self._mapping_path = Path(mapping_path)
        self._mapping = mapping
        default_merchandise_path = (
            Path(__file__).resolve().parents[2]
            / "config" / "forecast_merchandise_sources.json"
        )
        self._merchandise_mapping_path = (
            Path(merchandise_mapping_path)
            if merchandise_mapping_path is not None
            else (None if merchandise_mapping is not None else default_merchandise_path)
        )
        if merchandise_mapping is not None:
            self._merchandise_mapping = dict(merchandise_mapping)
        else:
            self._merchandise_mapping = json.loads(
                self._merchandise_mapping_path.read_text(encoding="utf-8")
            )
        self._merchandise_mapping_hash = mapping_hash(self._merchandise_mapping)
        self._merchandise_mapping_version = str(
            self._merchandise_mapping.get("mapping_version") or ""
        ).strip()
        if not self._merchandise_mapping_version:
            raise ValueError("forecast merchandise mapping_version is required")
        if not 30 <= max_execution_seconds <= 1500:
            raise ValueError("forecast execution budget must be 30-1500 seconds")
        if (not isinstance(max_sync_months, int) or isinstance(max_sync_months, bool)
                or not 1 <= max_sync_months <= V1_FORECAST_SYNC_MAX_MONTHS):
            raise ValueError(
                f"forecast synchronous scope must be 1-{V1_FORECAST_SYNC_MAX_MONTHS} months"
            )
        self._max_execution_seconds = max_execution_seconds
        self._max_sync_months = max_sync_months

    def generate(self, session_id: str, request: ForecastGenerateRequest) -> ForecastGenerateResponse:
        principal = self._sessions.require_admin(session_id)
        canonical = self._validate(request)
        request_payload = asdict(canonical)
        request_payload.pop("idempotency_key", None)
        payload = {
            "request": request_payload,
            "provenance": self._provenance.as_dict(),
            "forecast_merchandise_source": {
                "mapping_version": self._merchandise_mapping_version,
                "mapping_hash": self._merchandise_mapping_hash,
            },
        }
        fingerprint = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        try:
            reservation = self._gateway.reserve(actor=principal.actor_id, request=canonical,
                payload=payload, fingerprint=fingerprint, provenance=self._provenance)
        except BffError:
            raise
        except Exception as exc:
            message = str(exc).upper()
            if "IDEMPOTENCY_CONFLICT" in message:
                raise BffError(ApiErrorCode.IDEMPOTENCY_CONFLICT,
                    "Idempotency key was already used for a different forecast") from exc
            if "MODEL_NOT_FOUND" in message:
                raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model not found") from exc
            if "MODEL_NOT_AVAILABLE" in message or "MAPPING_NOT_AVAILABLE" in message:
                raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available") from exc
            if "FORECAST_IN_PROGRESS" in message:
                raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Forecast generation is already in progress") from exc
            if "INGESTION_CLEANUP_REQUIRED" in message:
                raise BffError(ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                               "Forecast cleanup requires administrator attention") from exc
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Forecast generation is temporarily unavailable") from exc

        if reservation.status == "completed":
            existing = self._gateway.get_model(reservation.model_id)
            if existing is None:
                raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Completed forecast model is missing")
            self._gateway.verify_generated(reservation.model_id, str(existing["workbook_sha256"]))
            return self._response(reservation, existing, True, canonical.start_month,
                                  canonical.end_month, canonical.base_model_id, fingerprint)
        if mapping_hash(self._mapping_path) != self._provenance.mapping_hash:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                           "Forecast mapping provenance is invalid")
        if (
            self._merchandise_mapping_path is not None
            and mapping_hash(self._merchandise_mapping_path) != self._merchandise_mapping_hash
        ):
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Forecast merchandise source provenance is invalid",
            )
        if reservation.status != "reserved" or not reservation.lease_token:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                           "Forecast reservation contract is invalid")
        if reservation.base_bucket != "pnl-models" or reservation.base_path != f"models/{canonical.base_model_id}/source.xlsx":
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                           "Base model Storage binding is invalid")

        storage_written = False
        finalized = False
        permit_token: str | None = None
        started = time.monotonic()
        policy = temp_artifact_policy()
        policy.ensure_capacity(MAX_FORECAST_WORKBOOK_BYTES * 3)
        with tempfile.TemporaryDirectory(prefix="pnl-forecast-", dir=policy.root) as directory:
            root = Path(directory)
            base = root / "base.xlsx"
            final = root / "forecast.xlsx"
            try:
                if hasattr(self._gateway, "acquire_execution_permit"):
                    permit_token = self._gateway.acquire_execution_permit(reservation.generation_id)
                base_bytes = self._gateway.download_base(reservation)
                if not base_bytes or len(base_bytes) > MAX_FORECAST_WORKBOOK_BYTES:
                    raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Base model size is invalid")
                if hashlib.sha256(base_bytes).hexdigest() != reservation.base_sha256:
                    raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Base model integrity check failed")
                base.write_bytes(base_bytes)
                mapping_snapshot = root / "model_mapping.json"
                # Freeze the already-loaded, provenance-validated mapping for
                # the whole operation; monthly engines never re-read live config.
                mapping_snapshot.write_bytes(canonical_json_bytes(self._mapping))
                merchandise_mapping_snapshot = root / "forecast_merchandise_sources.json"
                merchandise_mapping_snapshot.write_bytes(
                    canonical_json_bytes(self._merchandise_mapping)
                )
                source = base
                for index, month in enumerate(canonical.months):
                    if time.monotonic() - started > self._max_execution_seconds:
                        raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                                       "Forecast generation exceeded its execution budget")
                    if permit_token and hasattr(self._gateway, "renew_execution_permit"):
                        self._gateway.renew_execution_permit(reservation.generation_id, permit_token)
                    destination = final if index == len(canonical.months) - 1 else root / f"month-{month.month}.xlsx"
                    previous = source
                    try:
                        result = ForecastEngine(source, mapping_snapshot).run(
                            _engine_input(month), destination
                        )
                    except MerchandiseSourceValidationError as exc:
                        raise BffError(
                            ApiErrorCode.VALIDATION_ERROR,
                            "Forecast merchandise COGS source validation failed",
                            field_errors={"merchandise_cogs_source": exc.code},
                        ) from exc
                    except NewBusinessGoodsCogsValidationError as exc:
                        raise BffError(
                            ApiErrorCode.VALIDATION_ERROR,
                            "Forecast new-business merchandise mode validation failed",
                            field_errors={exc.field: exc.code},
                        ) from exc
                    if time.monotonic() - started > self._max_execution_seconds:
                        raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                                       "Forecast generation exceeded its execution budget")
                    if not result.validations or not all(bool(item.get("ok")) for item in result.validations):
                        raise BffError(ApiErrorCode.VALIDATION_ERROR, "Forecast validation failed")
                    source = destination
                    if previous != destination:
                        previous.unlink(missing_ok=True)
                if final.stat().st_size > MAX_FORECAST_WORKBOOK_BYTES:
                    raise BffError(ApiErrorCode.VALIDATION_ERROR, "Generated workbook exceeds 50 MB")
                generated_sha = hashlib.sha256(final.read_bytes()).hexdigest()
                # An upload response can be lost after Storage committed. Treat the
                # canonical path as possibly written before starting the call.
                storage_written = True
                self._gateway.upload_generated(reservation.model_id, final, generated_sha)
                self._gateway.verify_generated(reservation.model_id, generated_sha)
                period_types = extract_period_types(final)
                actual_year = infer_workbook_year(final, fallback_year=canonical.model_year)
                if actual_year != canonical.model_year:
                    raise BffError(ApiErrorCode.VALIDATION_ERROR, "Forecast model year does not match")
                try:
                    saved = self._gateway.finalize(reservation, sha256=generated_sha,
                        name=canonical.name, model_year=canonical.model_year,
                        version=canonical.version, file_name=f"forecast_{canonical.model_year}_{canonical.start_month:02d}_{canonical.end_month:02d}.xlsx",
                        period_types=period_types, provenance=self._provenance)
                except ForecastFinalizeUncertainError as exc:
                    # Never delete an object which may already be referenced by a committed Model.
                    finalized = True
                    try:
                        self._gateway.record_failure(reservation, cleanup_succeeded=False,
                                                     error_code="FORECAST_FINALIZE_UNCERTAIN")
                    except Exception:
                        pass
                    raise BffError(ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                                   "Forecast finalization requires administrator attention") from exc
                finalized = True
                if str(saved.get("workbook_sha256")) != generated_sha:
                    raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Generated model integrity check failed")
                return self._response(reservation, saved, reservation.replayed,
                                      canonical.start_month, canonical.end_month,
                                      canonical.base_model_id, fingerprint)
            except BffError:
                if finalized:
                    raise
                self._compensate(reservation, storage_written)
                raise
            except Exception as exc:
                if finalized:
                    raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Generated model response is invalid") from exc
                self._compensate(reservation, storage_written)
                raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Forecast generation failed") from exc
            finally:
                if permit_token and hasattr(self._gateway, "release_execution_permit"):
                    try:
                        self._gateway.release_execution_permit(reservation.generation_id, permit_token)
                    except Exception:
                        pass

    def _compensate(self, reservation: ForecastReservation, storage_written: bool) -> None:
        cleaned = True
        if storage_written:
            try: self._gateway.remove_generated(reservation.model_id)
            except Exception: cleaned = False
        try: self._gateway.record_failure(reservation, cleanup_succeeded=cleaned,
                                          error_code="FORECAST_GENERATION_FAILED")
        except Exception: cleaned = False
        if not cleaned:
            raise BffError(ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                           "Forecast cleanup requires administrator attention")

    def _validate(self, request: ForecastGenerateRequest) -> ForecastGenerateRequest:
        errors: dict[str, str] = {}
        try: base_id = str(uuid.UUID(request.base_model_id))
        except Exception: base_id = ""; errors["base_model_id"] = "must be a UUID"
        name = request.name.strip() if isinstance(request.name, str) else ""
        version = request.version.strip() if isinstance(request.version, str) else ""
        key = request.idempotency_key.strip() if isinstance(request.idempotency_key, str) else ""
        if not name or len(name) > 200 or any(ord(ch) < 32 for ch in name): errors["name"] = "must be safe text of 1-200 characters"
        if not version or len(version) > 64 or any(ord(ch) < 32 for ch in version): errors["version"] = "must be safe text of 1-64 characters"
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key): errors["idempotency_key"] = "invalid idempotency key"
        if not isinstance(request.model_year, int) or isinstance(request.model_year, bool) or not 2000 <= request.model_year <= 2200:
            errors["model_year"] = "must be 2000-2200"
        months_are_int = (isinstance(request.start_month, int) and not isinstance(request.start_month, bool)
            and isinstance(request.end_month, int) and not isinstance(request.end_month, bool))
        if not months_are_int or not 1 <= request.start_month <= request.end_month <= 12:
            errors["period"] = "must satisfy 1 <= start_month <= end_month <= 12"
        elif request.end_month - request.start_month + 1 > self._max_sync_months:
            raise BffError(
                ApiErrorCode.FORECAST_SCOPE_NOT_APPROVED,
                "Forecast request exceeds the approved synchronous scope",
                field_errors={
                    "period": f"must not exceed {self._max_sync_months} consecutive months",
                },
            )
        expected = tuple(range(request.start_month, request.end_month + 1)) if months_are_int else ()
        if tuple(item.month for item in request.months) != expected:
            errors["months"] = "must contain each selected month exactly once in order"
        selections: list[NewBusinessGoodsCogsSelection | None] = []
        for index, item in enumerate(request.months):
            selections.append(self._validate_month(item, errors, index))
        if errors: raise BffError(ApiErrorCode.VALIDATION_ERROR, "Forecast request is invalid", field_errors=errors)
        normalized_months = tuple(replace(item,
            sales=tuple(sorted(
                item.sales if any(
                    value.product_code == LC_MERCHANDISE_CODE for value in item.sales
                ) else item.sales + (ForecastSalesInput(LC_MERCHANDISE_CODE, 0, 0),),
                key=lambda value: value.product_code,
            )),
            production=tuple(sorted(item.production, key=lambda value: value.product_code)),
            mcm=tuple(sorted(item.mcm, key=lambda value: value.product_code)),
            manufacturing_adjustments=tuple(sorted(item.manufacturing_adjustments, key=lambda value: value.row)),
            sga_adjustments=tuple(sorted(item.sga_adjustments, key=lambda value: value.row)),
            new_business_goods_cogs_mode=selection.mode.value,
            new_business_goods_cogs=selection.manual_amount,
            new_business_goods_cogs_reason=selection.reason,
            new_business_goods_cogs_legacy_normalized=selection.legacy_normalized,
            sales_contract_version=FORECAST_SALES_CONTRACT_VERSION,
            lc_sales_mode=(
                LC_SALES_MODE_EXPLICIT
                if any(value.product_code == LC_MERCHANDISE_CODE for value in item.sales)
                else LC_SALES_MODE_LEGACY_PRODUCT_ONLY
            ),
        ) for item, selection in zip(request.months, selections) if selection is not None)
        return ForecastGenerateRequest(base_id, name, request.model_year, version,
            request.start_month, request.end_month, normalized_months, key)

    def _validate_month(
        self, item: ForecastMonthInput, errors: dict[str, str], index: int
    ) -> NewBusinessGoodsCogsSelection | None:
        selection: NewBusinessGoodsCogsSelection | None = None
        try:
            selection = normalize_new_business_goods_cogs(
                item.new_business_goods_cogs_mode,
                item.new_business_goods_cogs,
                item.new_business_goods_cogs_reason,
                legacy_normalized=item.new_business_goods_cogs_legacy_normalized,
            )
        except NewBusinessGoodsCogsValidationError as exc:
            errors[f"months.{index}.{exc.field}"] = exc.code
        if not isinstance(item.month, int) or isinstance(item.month, bool) or not 1 <= item.month <= 12:
            errors[f"months.{index}.month"] = "must be an integer from 1 through 12"
        sales_allowed = set(self._mapping.get("sales", {})) | {
            "UF_MBR", "IX", "OTHER", LC_MERCHANDISE_CODE,
        }
        legacy_sales_allowed = sales_allowed - {LC_MERCHANDISE_CODE}
        production_allowed = set(self._mapping.get("production", {}))
        mcm_allowed = set(self._mapping.get("mcm", {}))
        sales_codes = {x.product_code for x in item.sales}
        if sales_codes not in (sales_allowed, legacy_sales_allowed):
            errors[f"months.{index}.sales"] = "must include every canonical sales product exactly once"
        if {x.product_code for x in item.production} != production_allowed:
            errors[f"months.{index}.production"] = "must include every canonical production product exactly once"
        if {x.product_code for x in item.mcm} != mcm_allowed:
            errors[f"months.{index}.mcm"] = "must include every canonical MCM product exactly once"
        if len(sales_codes) != len(item.sales) or any(x.product_code not in sales_allowed for x in item.sales):
            errors[f"months.{index}.sales"] = "contains duplicate or unsupported product"
        if any(x.product_code not in production_allowed for x in item.production): errors[f"months.{index}.production"] = "unsupported product"
        if any(x.product_code not in mcm_allowed for x in item.mcm): errors[f"months.{index}.mcm"] = "unsupported product"
        allowed_mfg = {int(x) for x in self._mapping.get("manufacturing_input_rows", [])}
        allowed_sga = {int(x) for x in self._mapping.get("sga_input_rows", [])}
        if any(x.row not in allowed_mfg for x in item.manufacturing_adjustments): errors[f"months.{index}.manufacturing_adjustments"] = "unsupported row"
        if any(x.row not in allowed_sga for x in item.sga_adjustments): errors[f"months.{index}.sga_adjustments"] = "unsupported row"
        values: list[Any] = []
        nonnegative: list[Any] = []
        for x in item.sales: nonnegative += [x.quantity, x.amount]
        for x in item.production: nonnegative.append(x.quantity)
        for x in item.mcm: nonnegative.append(x.quantity)
        nonnegative += [item.uf_mbr_cogs_rate, item.ix_cogs_rate, item.uf_mbr_transport_rate,
            item.ix_transport_rate, item.ix_pack_liters, item.ix_pack_cost,
            item.plan_na_sa_sales, item.na_sa_sales, item.tariff_applicable_rate,
            item.tariff_rate, item.refund_rate]
        if item.new_business_goods_cogs is not None:
            nonnegative.append(item.new_business_goods_cogs)
        if item.raw_material_direct is not None: nonnegative.append(item.raw_material_direct)
        # Cost adjustments are signed deltas in the existing Streamlit workflow.
        values = nonnegative + [item.disposal_adjustment, item.obsolescence_adjustment,
            item.raw_material_adjustment] + [x.amount for x in item.manufacturing_adjustments] + [x.amount for x in item.sga_adjustments]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in values):
            errors[f"months.{index}"] = "all numeric values must be finite"
        if any(float(v) < 0 for v in nonnegative): errors[f"months.{index}"] = "quantities, amounts and rates must be nonnegative"
        if any(not 0 <= float(v) <= 1 for v in [item.uf_mbr_cogs_rate, item.ix_cogs_rate,
                item.uf_mbr_transport_rate, item.ix_transport_rate,
                item.tariff_applicable_rate, item.tariff_rate, item.refund_rate]):
            errors[f"months.{index}.rates"] = "rates must be between 0 and 1"
        if len({x.product_code for x in item.production}) != len(item.production) or len({x.product_code for x in item.mcm}) != len(item.mcm):
            errors[f"months.{index}.quantities"] = "duplicate product codes are not allowed"
        if len({x.row for x in item.manufacturing_adjustments}) != len(item.manufacturing_adjustments) or len({x.row for x in item.sga_adjustments}) != len(item.sga_adjustments):
            errors[f"months.{index}.adjustments"] = "duplicate adjustment rows are not allowed"
        reasons = [item.disposal_reason, item.obsolescence_reason,
            item.new_business_goods_cogs_reason, item.raw_material_reason]
        reasons += [x.reason for x in item.manufacturing_adjustments] + [x.reason for x in item.sga_adjustments]
        if any(not isinstance(reason, str) or len(reason) > 500 or any(ord(ch) < 32 and ch not in "\t" for ch in reason) for reason in reasons):
            errors[f"months.{index}.reasons"] = "reasons must be safe text up to 500 characters"
        if item.raw_material_basis not in {"model", "direct"} or (item.raw_material_basis == "direct" and item.raw_material_direct is None):
            errors[f"months.{index}.raw_material_basis"] = "direct basis requires raw_material_direct"
        if item.raw_material_basis == "model" and item.raw_material_direct is not None:
            errors[f"months.{index}.raw_material_direct"] = "must be null for model basis"
        ix_quantity = next((x.quantity for x in item.sales if x.product_code == "IX"), 0)
        if float(ix_quantity) > 0 and float(item.ix_pack_liters) <= 0:
            errors[f"months.{index}.ix_pack_liters"] = "must be positive when IX quantity is positive"
        return selection

    @staticmethod
    def _response(reservation: ForecastReservation, saved: Mapping[str, Any], replayed: bool,
                  start_month: int, end_month: int, base_model_id: str,
                  fingerprint: str) -> ForecastGenerateResponse:
        try:
            if (str(saved["id"]) != reservation.model_id
                or str(saved.get("source_kind")) != "forecast_generated"
                or str(saved.get("source_model_id")) != base_model_id
                or str(saved.get("forecast_generation_id")) != reservation.generation_id
                or str(saved.get("generation_input_fingerprint")) != fingerprint):
                raise ValueError("forecast model linkage mismatch")
            return ForecastGenerateResponse(reservation.generation_id, reservation.model_id,
                str(saved["name"]), int(saved["model_year"]), start_month, end_month,
                bool(saved["is_published"]), bool(saved["is_default"]),
                str(saved["workbook_sha256"]), replayed)
        except Exception as exc:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Generated model response is invalid") from exc


def _engine_input(value: ForecastMonthInput) -> ForecastInput:
    return ForecastInput(month=value.month,
        sales={x.product_code: SalesInput(x.quantity, x.amount) for x in value.sales},
        production={x.product_code: x.quantity for x in value.production},
        mcm={x.product_code: x.quantity for x in value.mcm},
        manufacturing_adjustments=[CostAdjustment(x.row, x.amount, x.reason) for x in value.manufacturing_adjustments],
        sga_adjustments=[CostAdjustment(x.row, x.amount, x.reason) for x in value.sga_adjustments],
        disposal_adjustment=value.disposal_adjustment, disposal_reason=value.disposal_reason,
        obsolescence_adjustment=value.obsolescence_adjustment, obsolescence_reason=value.obsolescence_reason,
        new_business_goods_cogs_mode=value.new_business_goods_cogs_mode,
        new_business_goods_cogs=value.new_business_goods_cogs,
        new_business_goods_cogs_reason=value.new_business_goods_cogs_reason,
        new_business_goods_cogs_legacy_normalized=value.new_business_goods_cogs_legacy_normalized,
        uf_mbr_cogs_rate=value.uf_mbr_cogs_rate, ix_cogs_rate=value.ix_cogs_rate,
        uf_mbr_transport_rate=value.uf_mbr_transport_rate, ix_transport_rate=value.ix_transport_rate,
        ix_pack_liters=value.ix_pack_liters, ix_pack_cost=value.ix_pack_cost,
        plan_na_sa_sales=value.plan_na_sa_sales, na_sa_sales=value.na_sa_sales,
        tariff_applicable_rate=value.tariff_applicable_rate, tariff_rate=value.tariff_rate,
        raw_material_basis=value.raw_material_basis, raw_material_direct=value.raw_material_direct,
        raw_material_adjustment=value.raw_material_adjustment, raw_material_reason=value.raw_material_reason,
        refund_rate=value.refund_rate,
        sales_contract_version=value.sales_contract_version,
        lc_sales_mode=value.lc_sales_mode)
