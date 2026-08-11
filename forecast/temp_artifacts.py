from __future__ import annotations

import os
import tempfile
import time
import threading
from dataclasses import dataclass
from pathlib import Path


OWNED_PREFIXES = ("pnl-model-", "pnl-forecast-", "pnl-evidence-", "pnl-parser-", "pnl-forecast-benchmark-")


@dataclass(frozen=True)
class TempArtifactPolicy:
    root: Path
    quota_bytes: int
    orphan_age_seconds: int = 24 * 60 * 60

    def __post_init__(self) -> None:
        resolved = self.root.resolve()
        if not resolved.is_absolute() or self.quota_bytes < 64 * 1024 * 1024:
            raise ValueError("invalid temp artifact policy")
        resolved.mkdir(parents=True, exist_ok=True)
        try:
            resolved.chmod(0o700)
        except OSError:
            pass
        object.__setattr__(self, "root", resolved)

    def ensure_capacity(self, additional_bytes: int = 0) -> None:
        if additional_bytes < 0 or self.owned_usage() + additional_bytes > self.quota_bytes:
            raise RuntimeError("temporary artifact quota exceeded")

    def owned_usage(self) -> int:
        total = 0
        for path in self._owned_paths():
            if path.is_symlink():
                continue
            if path.is_file():
                try: total += path.stat().st_size
                except FileNotFoundError: continue
            elif path.is_dir():
                for item in path.rglob("*"):
                    if item.is_symlink() or not item.is_file():
                        continue
                    try: total += item.stat().st_size
                    except FileNotFoundError: continue
        return total

    def make_file(self, *, prefix: str, suffix: str):
        self._validate_prefix(prefix)
        with _POLICY_LOCK:
            self.ensure_capacity()
            return tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False, dir=self.root)

    def make_directory(self, *, prefix: str) -> Path:
        self._validate_prefix(prefix)
        with _POLICY_LOCK:
            self.ensure_capacity()
            return Path(tempfile.mkdtemp(prefix=prefix, dir=self.root))

    def sweep(self, *, dry_run: bool = True, now: float | None = None) -> list[dict[str, object]]:
        current = time.time() if now is None else now
        report: list[dict[str, object]] = []
        for path in self._owned_paths():
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                continue
            if path.is_symlink():
                report.append({"path": path.name, "age_seconds": 0, "deleted": False,
                               "error": "unsafe_symlink"})
                continue
            age = current - metadata.st_mtime
            if age < self.orphan_age_seconds:
                continue
            try:
                resolved = path.resolve(strict=True)
            except FileNotFoundError:
                continue
            if resolved.parent != self.root or not resolved.name.startswith(OWNED_PREFIXES):
                raise RuntimeError("unsafe temporary artifact target")
            report.append({"path": resolved.name, "age_seconds": int(age), "deleted": not dry_run})
            if not dry_run:
                if resolved.is_dir():
                    import shutil
                    shutil.rmtree(resolved)
                else:
                    resolved.unlink(missing_ok=True)
        return report

    def _owned_paths(self) -> list[Path]:
        return [value for value in self.root.iterdir() if value.name.startswith(OWNED_PREFIXES)]

    @staticmethod
    def _validate_prefix(prefix: str) -> None:
        if prefix not in OWNED_PREFIXES:
            raise ValueError("unowned temporary artifact prefix")


_POLICY: TempArtifactPolicy | None = None
_POLICY_LOCK = threading.RLock()


def configure_temp_artifacts(root: str | Path, quota_bytes: int, orphan_age_seconds: int = 86400) -> TempArtifactPolicy:
    global _POLICY
    with _POLICY_LOCK:
        _POLICY = TempArtifactPolicy(Path(root), quota_bytes, orphan_age_seconds)
        # Starlette UploadFile and stdlib tempfile users share the owned root.
        tempfile.tempdir = str(_POLICY.root)
    return _POLICY


def temp_artifact_policy() -> TempArtifactPolicy:
    global _POLICY
    if _POLICY is None:
        _POLICY = TempArtifactPolicy(Path(tempfile.gettempdir()), 2 * 1024 * 1024 * 1024)
    return _POLICY


def temp_artifacts_configured() -> bool:
    return _POLICY is not None
