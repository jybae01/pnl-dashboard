from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .provenance import SHA256_PATTERN, mapping_hash


class MappingStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"


_ALLOWED_TRANSITIONS = {
    MappingStatus.DRAFT: {MappingStatus.DRAFT, MappingStatus.VALIDATED},
    MappingStatus.VALIDATED: {MappingStatus.VALIDATED, MappingStatus.PUBLISHED},
    MappingStatus.PUBLISHED: {MappingStatus.PUBLISHED},
}


@dataclass(frozen=True)
class MappingVersion:
    config_key: str
    version: str
    status: MappingStatus
    content: dict[str, Any]
    content_hash: str
    is_default: bool = False
    created_at: str = ""
    validated_at: str | None = None
    published_at: str | None = None

    def __post_init__(self) -> None:
        if not self.config_key.strip() or not self.version.strip():
            raise ValueError("config_key and version are required")
        if not SHA256_PATTERN.fullmatch(self.content_hash):
            raise ValueError("content_hash must be a lowercase SHA-256 hex digest")
        if mapping_hash(self.content) != self.content_hash:
            raise ValueError("content_hash does not match mapping content")
        if self.is_default and self.status is not MappingStatus.PUBLISHED:
            raise ValueError("only a published mapping can be the default")

    @classmethod
    def draft(cls, config_key: str, version: str, content: Mapping[str, Any]) -> "MappingVersion":
        payload = dict(content)
        return cls(
            config_key=config_key,
            version=version,
            status=MappingStatus.DRAFT,
            content=payload,
            content_hash=mapping_hash(payload),
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

    def transition(self, status: MappingStatus, *, is_default: bool = False) -> "MappingVersion":
        if status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"invalid mapping transition: {self.status.value} -> {status.value}")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        payload = asdict(self)
        payload["status"] = status
        payload["is_default"] = bool(is_default)
        if status is MappingStatus.VALIDATED and not payload["validated_at"]:
            payload["validated_at"] = now
        if status is MappingStatus.PUBLISHED:
            if not payload["validated_at"]:
                raise ValueError("a mapping must be validated before publication")
            payload["published_at"] = now
        return MappingVersion(**payload)


class LocalMappingConfigRepository:
    """Small local registry mirroring app_config draft/validate/publish semantics."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[MappingVersion]:
        if not self.path.exists():
            return []
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        return [MappingVersion(**{**row, "status": MappingStatus(row["status"])}) for row in rows]

    def _save(self, versions: list[MappingVersion]) -> None:
        payload = []
        for version in versions:
            row = asdict(version)
            row["status"] = version.status.value
            payload.append(row)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def create_draft(self, config_key: str, version: str, content: Mapping[str, Any]) -> MappingVersion:
        versions = self._load()
        if any(item.config_key == config_key and item.version == version for item in versions):
            raise ValueError(f"mapping version already exists: {config_key}@{version}")
        draft = MappingVersion.draft(config_key, version, content)
        self._save([*versions, draft])
        return draft

    def validate(self, config_key: str, version: str) -> MappingVersion:
        return self._transition(config_key, version, MappingStatus.VALIDATED)

    def publish(self, config_key: str, version: str, *, is_default: bool = True) -> MappingVersion:
        return self._transition(config_key, version, MappingStatus.PUBLISHED, is_default=is_default)

    def get_published(self, config_key: str) -> MappingVersion | None:
        candidates = [
            item for item in self._load()
            if item.config_key == config_key and item.status is MappingStatus.PUBLISHED
        ]
        if not candidates:
            return None
        return next((item for item in candidates if item.is_default), candidates[-1])

    def _transition(
        self,
        config_key: str,
        version: str,
        status: MappingStatus,
        *,
        is_default: bool = False,
    ) -> MappingVersion:
        versions = self._load()
        changed: MappingVersion | None = None
        output: list[MappingVersion] = []
        for item in versions:
            if is_default and item.config_key == config_key and item.is_default:
                item = MappingVersion(**{**asdict(item), "is_default": False})
            if item.config_key == config_key and item.version == version:
                item = item.transition(status, is_default=is_default)
                changed = item
            output.append(item)
        if changed is None:
            raise KeyError(f"{config_key}@{version}")
        self._save(output)
        return changed
