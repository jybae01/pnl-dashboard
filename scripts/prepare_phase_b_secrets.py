from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


GENERATED = {
    "viewer_code": 24,
    "admin_code": 24,
    "actor_namespace_secret": 32,
    "csrf_secret": 32,
}


def prepare(directory: Path) -> tuple[str, ...]:
    directory = directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    supabase_secret = directory / "supabase_secret_key"
    if not supabase_secret.is_file() or not supabase_secret.read_text(encoding="utf-8").strip():
        raise RuntimeError(
            "create a non-empty supabase_secret_key file in the controlled directory first"
        )
    existing = [name for name in GENERATED if (directory / name).exists()]
    if existing:
        raise RuntimeError("refusing to overwrite existing generated secret files")
    created = []
    try:
        for name, byte_count in GENERATED.items():
            path = directory / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, (secrets.token_urlsafe(byte_count) + "\n").encode("utf-8"))
            finally:
                os.close(descriptor)
            os.chmod(path, 0o600)
            created.append(path)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return tuple(path.name for path in created)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate local Phase B non-Supabase secrets without printing values."
    )
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args(argv)
    names = prepare(args.directory)
    print("created=" + ",".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
