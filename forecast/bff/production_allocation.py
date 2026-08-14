"""Forecast production allocation boundary.

The browser-facing forecast form uses business dimensions (process, product
group and unit), while :class:`~forecast.engine.ForecastInput` requires the
eight production keys used by the Golden Workbook.  This module is the small
adapter between those two contracts.  It deliberately does not modify the
engine or infer a ratio from sales, another month, or a fixed 50:50 policy.

The pure adapter accepts verified base-model quantities, making it useful in
unit tests and in other trusted callers.  ``ForecastProductionAllocationService``
owns the BFF checks around that adapter: session capability, model publication
and mapping provenance, workbook SHA verification, and same-month extraction.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from ..provenance import SHA256_PATTERN, ResultProvenance
from ..workbook import GoldenWorkbook, MONTH_COLUMNS
from .errors import ApiErrorCode, BffError


# Keep the public order aligned with the existing forecast form.  The engine
# itself consumes a mapping, but a stable sequence is useful for fingerprints,
# tests and transport adapters.
CANONICAL_PRODUCTION_CODES: tuple[str, ...] = (
    "SW400",
    "SW440",
    "BW400",
    "BW440",
    "LC",
    "FS_SW",
    "FS_BW",
    "FS_TW",
)

CANONICAL_PRODUCTION_UNITS: Mapping[str, str] = {
    "SW400": "PCS",
    "SW440": "PCS",
    "BW400": "PCS",
    "BW440": "PCS",
    "LC": "PCS",
    "FS_SW": "m",
    "FS_BW": "m",
    "FS_TW": "m",
}

FRONT_PROCESS = "전공정"
BACK_PROCESS = "후공정"
UNIT_PCS = "PCS"
UNIT_LENGTH_M = "m"

# Business dimensions are intentionally strict.  The Korean process names are
# the canonical labels used by the existing manufacturing presentation.
_DIMENSION_MAP: Mapping[tuple[str, str], tuple[str, str]] = {
    (FRONT_PROCESS, "SW"): ("FS_SW", UNIT_LENGTH_M),
    (FRONT_PROCESS, "BW"): ("FS_BW", UNIT_LENGTH_M),
    (FRONT_PROCESS, "TW"): ("FS_TW", UNIT_LENGTH_M),
    (BACK_PROCESS, "SW"): ("SW400", UNIT_PCS),
    (BACK_PROCESS, "BW"): ("BW400", UNIT_PCS),
    (BACK_PROCESS, "LC"): ("LC", UNIT_PCS),
}

_RATIO_PAIRS: Mapping[str, tuple[str, str]] = {
    "SW": ("SW400", "SW440"),
    "BW": ("BW400", "BW440"),
}


class ProductionAllocationValidationError(ValueError):
    """Invalid business production input or an invalid pure-adapter call."""

    def __init__(self, message: str = "Production input is invalid", *, field_errors: Mapping[str, str] | None = None):
        super().__init__(message)
        self.field_errors = dict(field_errors or {})


class BaseProductionIntegrityError(ValueError):
    """Missing/invalid base quantities or an invalid base source."""

    def __init__(self, message: str = "Base model production values are unavailable"):
        super().__init__(message)


@dataclass(frozen=True)
class BusinessProductionInput:
    """One business-level production entry.

    ``quantity`` accepts ``int``, ``float`` and ``Decimal`` values that the
    existing float-based Engine contract can represent without changing the
    numeric value.  The adapter converts through ``Decimal(str(value))`` so
    binary floating-point artifacts never decide a rounded split.
    """

    month: int
    process: str
    product_group: str
    quantity: int | float | Decimal
    unit: str


@dataclass(frozen=True)
class BusinessProductionTotal:
    """Immutable, normalized business total retained in allocation evidence."""

    process: str
    product_group: str
    quantity: Decimal
    unit: str


@dataclass(frozen=True)
class CanonicalProductionQuantity:
    """One canonical Engine production quantity."""

    product_code: str
    quantity: Decimal
    unit: str


@dataclass(frozen=True)
class ProductionAllocationResult:
    """Immutable allocation evidence for one month and selected base model."""

    base_model_id: str | None
    month: int
    base_workbook_sha256: str | None
    source_sw_pair: tuple[Decimal, Decimal] | None
    source_bw_pair: tuple[Decimal, Decimal] | None
    business_totals: tuple[BusinessProductionTotal, ...]
    canonical_quantities: tuple[CanonicalProductionQuantity, ...]

    def __post_init__(self) -> None:
        if tuple(row.product_code for row in self.canonical_quantities) != CANONICAL_PRODUCTION_CODES:
            raise ValueError("canonical production result must contain exactly eight products in order")

    def as_mapping(self) -> dict[str, Decimal]:
        """Return the exact eight-key mapping expected by the Engine adapter."""

        return {item.product_code: item.quantity for item in self.canonical_quantities}

    def as_engine_mapping(self) -> dict[str, float]:
        """Return the float mapping consumed by the existing Forecast Engine."""

        return {code: float(value) for code, value in self.as_mapping().items()}


@dataclass(frozen=True)
class ProductionAllocationBatch(Sequence[ProductionAllocationResult]):
    """Immutable multi-month result with convenient single-month forwarding."""

    results: tuple[ProductionAllocationResult, ...]

    def __post_init__(self) -> None:
        if not self.results:
            raise ValueError("allocation batch must not be empty")

    def __len__(self) -> int:
        return len(self.results)

    def __getitem__(self, index: int) -> ProductionAllocationResult:
        return self.results[index]

    def __iter__(self) -> Iterator[ProductionAllocationResult]:
        return iter(self.results)

    @property
    def months(self) -> tuple[int, ...]:
        return tuple(result.month for result in self.results)


def _decimal(value: Any, *, nonnegative: bool, what: str) -> Decimal:
    """Convert an accepted numeric value without allowing bool/NaN/Infinity."""

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ProductionAllocationValidationError(field_errors={what: "must be a finite nonnegative number"})
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ProductionAllocationValidationError(field_errors={what: "must be a finite nonnegative number"}) from None
    try:
        engine_value = float(number)
    except (OverflowError, ValueError):
        engine_value = math.inf
    try:
        engine_round_trip = Decimal(str(engine_value))
    except (InvalidOperation, ValueError):
        engine_round_trip = Decimal("NaN")
    if (
        not number.is_finite()
        or not math.isfinite(engine_value)
        or engine_round_trip != number
        or (nonnegative and number < 0)
    ):
        raise ProductionAllocationValidationError(field_errors={what: "must be a finite nonnegative number"})
    return number


def _month(value: Any, field: str = "month") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 12:
        raise ProductionAllocationValidationError(field_errors={field: "must be an integer from 1 through 12"})
    return value


def _normalize_inputs(inputs: BusinessProductionInput | Iterable[BusinessProductionInput]) -> tuple[BusinessProductionInput, ...]:
    if isinstance(inputs, BusinessProductionInput):
        values = (inputs,)
    else:
        if isinstance(inputs, (str, bytes, Mapping)):
            raise ProductionAllocationValidationError(field_errors={"inputs": "must be a sequence of production entries"})
        try:
            values = tuple(inputs)
        except TypeError:
            raise ProductionAllocationValidationError(field_errors={"inputs": "must be a sequence of production entries"}) from None
    if not values:
        raise ProductionAllocationValidationError(field_errors={"inputs": "must contain at least one entry"})
    for index, value in enumerate(values):
        if not isinstance(value, BusinessProductionInput):
            raise ProductionAllocationValidationError(
                field_errors={f"inputs.{index}": "must be a BusinessProductionInput"},
            )
    return values


def _validate_business_row(value: BusinessProductionInput, index: int) -> tuple[int, tuple[str, str], Decimal]:
    month = _month(value.month, f"inputs.{index}.month")
    if not isinstance(value.process, str) or not isinstance(value.product_group, str):
        raise ProductionAllocationValidationError(
            field_errors={f"inputs.{index}.dimension": "process and product group must be strings"},
        )
    key = (value.process, value.product_group)
    if key not in _DIMENSION_MAP:
        raise ProductionAllocationValidationError(
            field_errors={f"inputs.{index}.dimension": "unsupported process/product group"},
        )
    expected_code, expected_unit = _DIMENSION_MAP[key]
    if not isinstance(value.unit, str) or value.unit != expected_unit:
        raise ProductionAllocationValidationError(
            field_errors={f"inputs.{index}.unit": f"must be {expected_unit}"},
        )
    quantity = _decimal(value.quantity, nonnegative=True, what=f"inputs.{index}.quantity")
    return month, key, quantity


def _quantum(value: Decimal) -> Decimal:
    # Decimal.as_tuple().exponent is an int for finite values.  A zero quantum
    # means integral PCS and yields deterministic half-up integer rounding.
    # Positive exponents represent an integer with trailing zeroes (for
    # example Decimal("1E+3")); PCS business quantities must still round to
    # whole units, never to thousands.  Decimal(1) is therefore the coarsest
    # public quantum.
    exponent = min(int(value.as_tuple().exponent), 0)
    return Decimal(1).scaleb(exponent)


def _rounded_split(total: Decimal, first_base: Decimal, second_base: Decimal, *, field: str) -> tuple[Decimal, Decimal]:
    """Split ``total`` and preserve its Decimal quantum and exact sum.

    The first (400) product is rounded half-up to the input total's quantum;
    the second product is always the exact remainder.  Thus 101 at a 1/3
    ratio becomes (34, 67), while a quantity such as ``1.00`` remains at the
    hundredths quantum.  No binary floating-point sum or iteration order can
    alter the result.
    """

    if total == 0:
        quantum = _quantum(total)
        return Decimal(0).quantize(quantum), Decimal(0).quantize(quantum)
    denominator = first_base + second_base
    if denominator <= 0:
        raise BaseProductionIntegrityError("Base model production ratio is unavailable")
    quantum = _quantum(total)
    integer_digits = max(1, total.adjusted() + 1)
    with localcontext() as context:
        # The default Decimal precision (28) is too small for a valid finite
        # float such as 1e308 when the public quantum is a whole unit.
        context.prec = max(28, integer_digits + 32)
        ratio = first_base / denominator
        first = (total * ratio).quantize(quantum, rounding=ROUND_HALF_UP)
        second = total - first
        # Quantizing the remainder is normally a no-op, but protects a Decimal
        # context with a finer exponent from changing the public quantum.
        second = second.quantize(quantum)
    return first, second


def _base_for_month(base_quantities: Mapping[Any, Any] | None, month: int) -> Mapping[str, Any]:
    if base_quantities is None:
        return {}
    if not isinstance(base_quantities, Mapping):
        raise BaseProductionIntegrityError()
    # The month key is mandatory even for a single-month call.  Accepting a
    # direct {code: value} map would let a multi-month caller accidentally
    # reuse one month's ratio.
    if month in base_quantities or str(month) in base_quantities:
        value = base_quantities.get(month, base_quantities.get(str(month)))
        if not isinstance(value, Mapping):
            raise BaseProductionIntegrityError()
        return value
    return {}


def _validated_base_pair(base: Mapping[str, Any], pair: tuple[str, str]) -> tuple[Decimal, Decimal]:
    values: list[Decimal] = []
    for code in pair:
        if code not in base:
            raise BaseProductionIntegrityError("Base model production values are unavailable")
        try:
            values.append(_decimal(base[code], nonnegative=True, what="base"))
        except ProductionAllocationValidationError:
            raise BaseProductionIntegrityError("Base model production values are invalid") from None
    return values[0], values[1]


def _result_for_month(
    rows: Sequence[tuple[BusinessProductionInput, tuple[str, str], Decimal]],
    *,
    month: int,
    base_quantities: Mapping[Any, Any] | None,
    base_model_id: str | None,
    base_workbook_sha256: str | None,
) -> ProductionAllocationResult:
    totals: dict[tuple[str, str], tuple[Decimal, str]] = {}
    seen: set[tuple[str, str]] = set()
    for original, key, quantity in rows:
        if key in seen:
            raise ProductionAllocationValidationError(
                field_errors={"inputs": "duplicate process/product group"},
            )
        seen.add(key)
        totals[key] = (quantity, original.unit)

    base = _base_for_month(base_quantities, month)
    canonical: dict[str, Decimal] = {code: Decimal(0) for code in CANONICAL_PRODUCTION_CODES}
    source_sw: tuple[Decimal, Decimal] | None = None
    source_bw: tuple[Decimal, Decimal] | None = None

    for (process, group), (total, _unit) in totals.items():
        code, _expected_unit = _DIMENSION_MAP[(process, group)]
        if process == BACK_PROCESS and group in _RATIO_PAIRS:
            pair = _RATIO_PAIRS[group]
            # A zero total is intentionally independent of ratio availability.
            if total == 0:
                first, second = _rounded_split(total, Decimal(0), Decimal(0), field=group)
                source = None
            else:
                source = _validated_base_pair(base, pair)
                first, second = _rounded_split(total, source[0], source[1], field=group)
            canonical[pair[0]] = first
            canonical[pair[1]] = second
            if group == "SW":
                source_sw = source
            else:
                source_bw = source
        else:
            canonical[code] = total

    business_totals = tuple(
        BusinessProductionTotal(process=process, product_group=group, quantity=quantity, unit=unit)
        for (process, group), (quantity, unit) in sorted(totals.items())
    )
    output = tuple(
        CanonicalProductionQuantity(code, canonical[code], CANONICAL_PRODUCTION_UNITS[code])
        for code in CANONICAL_PRODUCTION_CODES
    )
    return ProductionAllocationResult(
        base_model_id=base_model_id,
        month=month,
        base_workbook_sha256=base_workbook_sha256,
        source_sw_pair=source_sw,
        source_bw_pair=source_bw,
        business_totals=business_totals,
        canonical_quantities=output,
    )


def allocate_production(
    inputs: BusinessProductionInput | Iterable[BusinessProductionInput],
    base_quantities: Mapping[Any, Any] | None = None,
    *,
    base_model_id: str | None = None,
    base_workbook_sha256: str | None = None,
) -> ProductionAllocationResult | ProductionAllocationBatch:
    """Convert business production rows into exact canonical quantities.

    A one-month input returns ``ProductionAllocationResult``.  A multi-month
    input returns an immutable ``ProductionAllocationBatch`` sorted by month.
    Ratios are selected only from ``base_quantities[month]`` and only for the
    corresponding SW/BW pair.
    """

    values = _normalize_inputs(inputs)
    checked: list[tuple[BusinessProductionInput, tuple[str, str], Decimal]] = []
    for index, value in enumerate(values):
        month, key, quantity = _validate_business_row(value, index)
        checked.append((value, key, quantity))
    # Duplicate checks are performed within each month; identical dimensions
    # in separate months are valid and intentionally use separate base ratios.
    grouped: dict[int, list[tuple[BusinessProductionInput, tuple[str, str], Decimal]]] = {}
    for value, key, quantity in checked:
        grouped.setdefault(value.month, []).append((value, key, quantity))
    results = tuple(
        _result_for_month(
            grouped[month], month=month, base_quantities=base_quantities,
            base_model_id=base_model_id, base_workbook_sha256=base_workbook_sha256,
        )
        for month in sorted(grouped)
    )
    return results[0] if len(results) == 1 else ProductionAllocationBatch(results)


def extract_base_month_quantities(
    workbook: GoldenWorkbook,
    month: int,
    mapping: Mapping[str, Any],
    *,
    required_codes: Iterable[str] | None = None,
) -> dict[str, Decimal]:
    """Read verified workbook production values for exactly one month.

    ``mapping['production']`` contains internal row numbers.  The returned
    dictionary intentionally contains only canonical product names; row and
    cell addresses never cross this module's error boundary.
    """

    month = _month(month)
    production = mapping.get("production") if isinstance(mapping, Mapping) else None
    if not isinstance(production, Mapping):
        raise BaseProductionIntegrityError("Base model production mapping is unavailable")
    if any(code not in CANONICAL_PRODUCTION_CODES for code in production):
        raise BaseProductionIntegrityError("Base model production mapping is invalid")
    required_raw = tuple(production.keys()) if required_codes is None else tuple(required_codes)
    unsupported = [code for code in required_raw if code not in CANONICAL_PRODUCTION_CODES]
    if unsupported:
        raise BaseProductionIntegrityError("Base model production mapping is invalid")
    required = tuple(code for code in CANONICAL_PRODUCTION_CODES if code in required_raw)
    column = MONTH_COLUMNS.get(month)
    if not column:
        raise BaseProductionIntegrityError("Base model month is unavailable")
    output: dict[str, Decimal] = {}
    for code in required:
        row = production.get(code)
        if isinstance(row, bool) or not isinstance(row, (int, str)):
            raise BaseProductionIntegrityError("Base model production mapping is invalid")
        try:
            row_number = int(row)
        except (TypeError, ValueError):
            raise BaseProductionIntegrityError("Base model production mapping is invalid") from None
        if row_number <= 0:
            raise BaseProductionIntegrityError("Base model production mapping is invalid")
        try:
            reader = getattr(workbook, "raw_value", None)
            raw = (reader or workbook.value)(f"{column}{row_number}")
        except Exception:
            raise BaseProductionIntegrityError("Base model production values are unavailable") from None
        try:
            output[code] = _decimal(raw, nonnegative=True, what="base")
        except ProductionAllocationValidationError:
            raise BaseProductionIntegrityError("Base model production values are invalid") from None
    return output


class ForecastProductionAllocationService:
    """Admin-only service over verified selected base-model production data."""

    def __init__(
        self,
        sessions: Any,
        model_repository: Any,
        mapping: Mapping[str, Any],
        provenance: ResultProvenance,
    ) -> None:
        self._sessions = sessions
        self._repository = model_repository
        self._mapping = dict(mapping)
        self._provenance = provenance

    def allocate(
        self,
        session_id: str,
        base_model_id: str,
        inputs: BusinessProductionInput | Iterable[BusinessProductionInput],
    ) -> ProductionAllocationResult | ProductionAllocationBatch:
        self._sessions.require_admin(session_id)
        normalized_id = self._normalize_model_id(base_model_id)
        model = self._require_model(normalized_id)
        # Validate business rows before opening the workbook, so invalid user
        # data consistently uses VALIDATION_ERROR rather than an integrity code.
        try:
            values = _normalize_inputs(inputs)
            checked: list[tuple[BusinessProductionInput, tuple[str, str], Decimal]] = []
            for index, value in enumerate(values):
                month, key, quantity = _validate_business_row(value, index)
                checked.append((value, key, quantity))
        except ProductionAllocationValidationError as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Production input is invalid",
                field_errors=exc.field_errors,
            ) from exc
        grouped: dict[int, list[tuple[BusinessProductionInput, tuple[str, str], Decimal]]] = {}
        for value, key, quantity in checked:
            grouped.setdefault(value.month, []).append((value, key, quantity))

        # Reject duplicate dimensions before opening the private workbook.
        for rows in grouped.values():
            keys = [key for _value, key, _quantity in rows]
            if len(keys) != len(set(keys)):
                raise BffError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "Production input is invalid",
                    field_errors={"inputs": "duplicate process/product group"},
                )

        source_path, source_sha = self._verified_source(model, normalized_id)

        try:
            workbook = GoldenWorkbook(source_path)
            month_base: dict[int, dict[str, Decimal]] = {}
            for month, rows in grouped.items():
                required: set[str] = set()
                for _value, (process, group), quantity in rows:
                    if process == BACK_PROCESS and group in _RATIO_PAIRS and quantity != 0:
                        required.update(_RATIO_PAIRS[group])
                month_base[month] = extract_base_month_quantities(
                    workbook, month, self._mapping, required_codes=required,
                )
        except BaseProductionIntegrityError as exc:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, str(exc)) from exc
        except Exception as exc:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Base model production source is unavailable") from exc

        try:
            return allocate_production(
                values, month_base, base_model_id=normalized_id,
                base_workbook_sha256=source_sha,
            )
        except ProductionAllocationValidationError as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Production input is invalid",
                field_errors=exc.field_errors,
            ) from exc
        except BaseProductionIntegrityError as exc:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, str(exc)) from exc

    @staticmethod
    def _normalize_model_id(value: Any) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except Exception:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Base model id is invalid",
                field_errors={"base_model_id": "must be a UUID"},
            ) from None

    def _require_model(self, model_id: str) -> Any:
        try:
            model = self._repository.get(model_id)
        except Exception as exc:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available") from exc
        if model is None:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available")
        try:
            if str(uuid.UUID(str(getattr(model, "id")))) != model_id:
                raise ValueError("selected model id mismatch")
        except Exception as exc:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available") from exc
        if not bool(getattr(model, "is_published", False)):
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available")
        if str(getattr(model, "mapping_status", "")) != "published":
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available")
        if str(getattr(model, "mapping_version", "")) != self._provenance.mapping_version:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available")
        if str(getattr(model, "mapping_hash", "")) != self._provenance.mapping_hash:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Base model is not available")
        return model

    def _verified_source(self, model: Any, model_id: str) -> tuple[Path, str]:
        recorded = str(getattr(model, "workbook_sha256", "") or "")
        if not SHA256_PATTERN.fullmatch(recorded):
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Base model source integrity is unavailable")
        try:
            path = Path(self._repository.path(model_id))
            content = path.read_bytes()
        except Exception as exc:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Base model source is unavailable") from exc
        actual = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(actual, recorded):
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Base model source integrity check failed")
        return path, recorded


__all__ = [
    "CANONICAL_PRODUCTION_CODES",
    "CANONICAL_PRODUCTION_UNITS",
    "FRONT_PROCESS",
    "BACK_PROCESS",
    "UNIT_PCS",
    "UNIT_LENGTH_M",
    "BusinessProductionInput",
    "BusinessProductionTotal",
    "CanonicalProductionQuantity",
    "ProductionAllocationBatch",
    "ProductionAllocationResult",
    "ProductionAllocationValidationError",
    "BaseProductionIntegrityError",
    "ForecastProductionAllocationService",
    "allocate_production",
    "extract_base_month_quantities",
]
