from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Mapping[str, Any] | list[Any]) -> bytes:
    """Return deterministic JSON bytes used for mapping/result fingerprints."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def mapping_hash(value: Mapping[str, Any] | str | Path) -> str:
    if isinstance(value, (str, Path)):
        payload = json.loads(Path(value).read_text(encoding="utf-8"))
    else:
        payload = value
    return sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class ResultProvenance:
    engine_version: str
    mapping_version: str
    mapping_hash: str
    result_schema_version: str

    def __post_init__(self) -> None:
        for field_name in ("engine_version", "mapping_version", "result_schema_version"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if not SHA256_PATTERN.fullmatch(self.mapping_hash):
            raise ValueError("mapping_hash must be a lowercase SHA-256 hex digest")

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def load_result_provenance(
    mapping_path: str | Path,
    *,
    mapping_version: str,
    engine_version: str,
    result_schema_version: str = "1",
) -> ResultProvenance:
    return ResultProvenance(
        engine_version=engine_version,
        mapping_version=mapping_version,
        mapping_hash=mapping_hash(mapping_path),
        result_schema_version=result_schema_version,
    )


def load_registered_provenance(
    mapping_path: str | Path,
    registry_path: str | Path,
    release_path: str | Path,
) -> ResultProvenance:
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    release = json.loads(Path(release_path).read_text(encoding="utf-8"))
    active_version = str(registry["active_version"])
    active = next(
        item for item in registry["versions"]
        if str(item["version"]) == active_version and item["status"] == "published"
    )
    actual_hash = mapping_hash(mapping_path)
    if active["content_hash"] != actual_hash:
        raise ValueError("active mapping hash does not match model_mapping.json")
    return ResultProvenance(
        engine_version=str(release["version"]),
        mapping_version=active_version,
        mapping_hash=actual_hash,
        result_schema_version=str(registry.get("schema_version", "1")),
    )
