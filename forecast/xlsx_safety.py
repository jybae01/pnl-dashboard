from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import stat
from typing import TypeAlias
import xml.etree.ElementTree as ET
import zipfile


MAX_WORKBOOK_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 5_000
MAX_ZIP_ENTRY_BYTES = 256 * 1024 * 1024
MAX_ZIP_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 1_000
MAX_INSPECTED_XML_BYTES = 16 * 1024 * 1024
MAX_INSPECTED_XML_TOTAL_BYTES = 64 * 1024 * 1024
REQUIRED_XLSX_PARTS = frozenset(
    {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"}
)

XlsxSource: TypeAlias = str | Path | bytes | bytearray


@dataclass(frozen=True)
class XlsxPackagePolicy:
    forbidden_entries: frozenset[str] = frozenset()
    forbidden_prefixes: tuple[str, ...] = ()
    inspect_xml_safety: bool = False
    forbid_external_relationships: bool = False


STRICT_REPORTING_XLSX_POLICY = XlsxPackagePolicy(
    forbidden_entries=frozenset({"xl/vbaproject.bin"}),
    forbidden_prefixes=(
        "xl/externallinks/",
        "xl/embeddings/",
        "xl/activex/",
        "xl/ctrlprops/",
    ),
    inspect_xml_safety=True,
    forbid_external_relationships=True,
)


class XlsxPackageError(ValueError):
    """An XLSX package failed a safe, user-facing structural check."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate_xlsx_package(
    source: XlsxSource,
    *,
    file_name: str,
    policy: XlsxPackagePolicy = XlsxPackagePolicy(),
) -> None:
    """Validate ZIP/package safety without applying workbook business semantics."""

    _validate_file_name(file_name)
    zip_source = _normalize_source(source)
    try:
        with zipfile.ZipFile(zip_source) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise XlsxPackageError("too_many_entries")

            names: set[str] = set()
            folded_names: set[str] = set()
            expanded = 0
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                folded = name.casefold()
                if (
                    name in names
                    or folded in folded_names
                    or name.startswith("/")
                    or any(part == ".." for part in name.split("/"))
                ):
                    raise XlsxPackageError("unsafe_or_duplicate_entry")
                names.add(name)
                folded_names.add(folded)
                if entry.flag_bits & 0x1:
                    raise XlsxPackageError("encrypted_entry")
                mode = entry.external_attr >> 16
                if mode and stat.S_ISLNK(mode):
                    raise XlsxPackageError("symlink_entry")
                if entry.file_size > MAX_ZIP_ENTRY_BYTES:
                    raise XlsxPackageError("entry_too_large")
                expanded += entry.file_size
                if expanded > MAX_ZIP_EXPANDED_BYTES:
                    raise XlsxPackageError("expanded_package_too_large")
                ratio = entry.file_size / max(entry.compress_size, 1)
                if ratio > MAX_ZIP_COMPRESSION_RATIO:
                    raise XlsxPackageError("compression_ratio_too_high")

            if not REQUIRED_XLSX_PARTS.issubset(names):
                raise XlsxPackageError("required_ooxml_parts_missing")
            if policy.forbidden_entries.intersection(folded_names):
                raise XlsxPackageError("unsafe_ooxml")
            if any(
                name.startswith(prefix)
                for name in folded_names
                for prefix in policy.forbidden_prefixes
            ):
                raise XlsxPackageError("unsafe_ooxml")
            if archive.testzip() is not None:
                raise XlsxPackageError("zip_crc_failed")
            if policy.inspect_xml_safety or policy.forbid_external_relationships:
                _inspect_xml_parts(archive, policy)
    except XlsxPackageError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise XlsxPackageError("invalid_xlsx") from exc


def _validate_file_name(file_name: str) -> None:
    if (
        not isinstance(file_name, str)
        or not file_name.strip()
        or len(file_name) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in file_name)
    ):
        raise XlsxPackageError("invalid_file_name")
    normalized = file_name.strip().replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if normalized != name or name in {"", ".", ".."}:
        raise XlsxPackageError("invalid_file_name")
    if Path(name).suffix.casefold() != ".xlsx":
        raise XlsxPackageError("only_xlsx")


def _normalize_source(source: XlsxSource) -> str | Path | BytesIO:
    if isinstance(source, (bytes, bytearray)):
        payload = bytes(source)
        if not payload:
            raise XlsxPackageError("upload_empty")
        if len(payload) > MAX_WORKBOOK_BYTES:
            raise XlsxPackageError("file_too_large")
        return BytesIO(payload)

    try:
        path = Path(source)
    except TypeError as exc:
        raise XlsxPackageError("invalid_source") from exc
    if not path.is_file():
        raise XlsxPackageError("upload_missing")
    size = path.stat().st_size
    if size <= 0:
        raise XlsxPackageError("upload_empty")
    if size > MAX_WORKBOOK_BYTES:
        raise XlsxPackageError("file_too_large")
    return path


def _inspect_xml_parts(archive: zipfile.ZipFile, policy: XlsxPackagePolicy) -> None:
    inspected = 0
    for entry in archive.infolist():
        name = entry.filename.replace("\\", "/")
        folded = name.casefold()
        if not folded.endswith((".xml", ".rels")):
            continue
        if entry.file_size > MAX_INSPECTED_XML_BYTES:
            raise XlsxPackageError("xml_part_too_large")
        inspected += entry.file_size
        if inspected > MAX_INSPECTED_XML_TOTAL_BYTES:
            raise XlsxPackageError("xml_inspection_limit")
        payload = archive.read(entry.filename)
        normalized = payload.lower()
        if b"<!doctype" in normalized or b"<!entity" in normalized:
            raise XlsxPackageError("unsafe_ooxml")
        if policy.forbid_external_relationships and folded.endswith(".rels"):
            try:
                relationships = ET.fromstring(payload)
            except ET.ParseError as exc:
                raise XlsxPackageError("malformed_ooxml") from exc
            if any(
                relation.tag.rsplit("}", 1)[-1] == "Relationship"
                and relation.attrib.get("TargetMode", "").strip().casefold() == "external"
                for relation in relationships.iter()
            ):
                raise XlsxPackageError("unsafe_external_relationship")
