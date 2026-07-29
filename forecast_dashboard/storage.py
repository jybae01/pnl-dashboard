"""Validated workbook persistence for local and Supabase deployments."""

from __future__ import annotations

import os
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Mapping

import streamlit as st


BUCKET_NAME = "mis-dashboard-data"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 2_000
ALLOWED_OBJECTS = frozenset({"saved_plan.xlsx", "saved_actual.xlsx"})


class StorageError(RuntimeError):
    """Raised for safe, user-displayable storage failures."""


def _validated_object_name(name: str) -> str:
    if name not in ALLOWED_OBJECTS:
        raise StorageError("???? ?? ??? ??????.")
    return name


def validate_xlsx(payload: bytes) -> None:
    if not payload:
        raise StorageError("? ??? ???? ? ????.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise StorageError("??? ??? 10MB ???? ???.")
    if not payload.startswith(b"PK"):
        raise StorageError("???? ?? ?? XLSX ??? ??? ???.")

    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise StorageError("?? ?? ?? ?? ?? ??? ??????.")
            if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
                raise StorageError("?? ?? ??? ?? ??? ??????.")
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or not any(
                name.startswith("xl/worksheets/") for name in names
            ):
                raise StorageError("???? XLSX ?? ??? ????.")
    except zipfile.BadZipFile as exc:
        raise StorageError("?????? ???? ?? XLSX ?????.") from exc


@st.cache_resource(show_spinner=False)
def _supabase_client(url: str, key: str):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise StorageError("Supabase ???? ???? ?????.") from exc
    return create_client(url, key)


def get_supabase_client(secrets: Mapping[str, object]):
    url = str(secrets.get("SUPABASE_URL", "")).strip()
    key = str(secrets.get("SUPABASE_KEY", "")).strip()
    if not url and not key:
        return None
    if not url or not key:
        raise StorageError("Supabase URL? ?? ?? ??? ???.")
    return _supabase_client(url, key)


def save_uploaded_data(
    name: str, payload: bytes, *, app_dir: Path, secrets: Mapping[str, object]
) -> str:
    object_name = _validated_object_name(name)
    validate_xlsx(payload)
    client = get_supabase_client(secrets)
    if client is not None:
        try:
            client.storage.from_(BUCKET_NAME).upload(
                object_name,
                payload,
                {
                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "upsert": "true",
                },
            )
        except Exception as exc:
            raise StorageError("?? ???? ??? ???? ?????.") from exc
        return "?? ???"

    data_dir = app_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / object_name
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=data_dir, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target)
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise StorageError("?? ???? ??? ???? ?????.") from exc
    return "?? ???"


def load_saved_data(
    name: str, *, app_dir: Path, secrets: Mapping[str, object]
) -> bytes | None:
    object_name = _validated_object_name(name)
    client = get_supabase_client(secrets)
    if client is not None:
        try:
            objects = client.storage.from_(BUCKET_NAME).list()
            if object_name not in {str(item.get("name", "")) for item in objects}:
                return None
            payload = client.storage.from_(BUCKET_NAME).download(object_name)
        except Exception as exc:
            raise StorageError("?? ????? ??? ???? ?????.") from exc
        validate_xlsx(payload)
        return payload

    target = app_dir / "data" / object_name
    if not target.is_file():
        return None
    payload = target.read_bytes()
    validate_xlsx(payload)
    return payload


def delete_saved_data(
    name: str, *, app_dir: Path, secrets: Mapping[str, object]
) -> None:
    object_name = _validated_object_name(name)
    client = get_supabase_client(secrets)
    if client is not None:
        try:
            client.storage.from_(BUCKET_NAME).remove([object_name])
        except Exception as exc:
            raise StorageError("?? ???? ??? ???? ?????.") from exc
        return
    (app_dir / "data" / object_name).unlink(missing_ok=True)
