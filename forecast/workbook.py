from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .formula import FormulaError, RangeValue, col_name, col_number, evaluate, normalize_ref, translate_formula

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NAMESPACES = {
    "": NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "x14": "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "x14ac": "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac",
    "xr": "http://schemas.microsoft.com/office/spreadsheetml/2014/revision",
    "xr2": "http://schemas.microsoft.com/office/spreadsheetml/2015/revision2",
    "xr3": "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3",
    "x15": "http://schemas.microsoft.com/office/spreadsheetml/2010/11/main",
    "x15ac": "http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac",
    "x16r2": "http://schemas.microsoft.com/office/spreadsheetml/2015/02/main",
    "xr6": "http://schemas.microsoft.com/office/spreadsheetml/2016/revision6",
    "xr10": "http://schemas.microsoft.com/office/spreadsheetml/2016/revision10",
}
for _prefix, _uri in NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)
Q = lambda name: f"{{{NS}}}{name}"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
AUDIT_SHEET_NAME = "입력반영내역"


def serialize_xml(
    root: ET.Element,
    required_prefixes: tuple[str, ...] = (),
    default_namespace: str | None = None,
) -> bytes:
    """Serialize without breaking mc:Ignorable namespace declarations.

    ElementTree omits namespace declarations that occur only inside the text
    value of mc:Ignorable. Desktop Excel treats that as workbook corruption.
    """
    text = ET.tostring(root, encoding="unicode", xml_declaration=False)
    if default_namespace:
        declaration = re.search(
            rf'xmlns:(?P<prefix>[A-Za-z_][\w.-]*)="{re.escape(default_namespace)}"',
            text,
        )
        if declaration:
            prefix = declaration.group("prefix")
            text = text.replace(f"<{prefix}:", "<").replace(f"</{prefix}:", "</")
            text = text.replace(
                f'xmlns:{prefix}="{default_namespace}"',
                f'xmlns="{default_namespace}"',
            )
    opening_end = text.find(">")
    opening = text[:opening_end]
    additions = []
    for prefix in required_prefixes:
        if f"xmlns:{prefix}=" not in opening:
            additions.append(f' xmlns:{prefix}="{NAMESPACES[prefix]}"')
    if additions:
        text = text[:opening_end] + "".join(additions) + text[opening_end:]
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n" + text).encode("utf-8")


@dataclass
class ChangeLog:
    cell: str
    old_value: Any
    new_value: Any
    source: str
    reason: str
    formula_overwritten: bool = False


class GoldenWorkbook:
    """OOXML adapter that changes only configured cells and preserves the package."""

    def __init__(self, path: str | Path, sheet_xml: str | None = None):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as archive:
            self.entries = {name: archive.read(name) for name in archive.namelist()}
        if sheet_xml is None:
            sheet_xml = self._default_model_sheet_xml()
        if sheet_xml not in self.entries:
            raise ValueError(f"워크북에서 모형 시트를 찾을 수 없습니다: {sheet_xml}")
        self.sheet_xml = sheet_xml
        self.shared_strings = self._read_shared_strings()
        self.root = ET.fromstring(self.entries[self.sheet_xml])

    def _default_model_sheet_xml(self) -> str:
        """Prefer the approved Data sheet even when a README sheet comes first."""
        for alias in ("Data", "DATA", "원본_Data", "원본데이터"):
            resolved = self._worksheet_target(self.entries, alias)
            if resolved is not None:
                return resolved[0]
        return "xl/worksheets/sheet1.xml"
        self.cells = {cell.attrib["r"].upper(): cell for cell in self.root.iter(Q("c"))}
        self.formulas: dict[str, str] = {}
        self._expand_formulas()
        self.original_formulas = dict(self.formulas)
        self.overrides: dict[str, Any] = {}
        self.cache: dict[str, Any] = {}
        self.stack: set[str] = set()
        self.log: list[ChangeLog] = []

    def _read_shared_strings(self) -> list[str]:
        raw = self.entries.get("xl/sharedStrings.xml")
        if not raw: return []
        root = ET.fromstring(raw)
        return ["".join(node.text or "" for node in item.iter(Q("t"))) for item in root.findall(Q("si"))]

    def _expand_formulas(self) -> None:
        anchors: dict[str, tuple[str, str]] = {}
        pending: list[tuple[str, str]] = []
        for addr, cell in self.cells.items():
            node = cell.find(Q("f"))
            if node is None: continue
            text = (node.text or "").strip()
            si = node.attrib.get("si")
            if node.attrib.get("t") == "shared" and si:
                if text:
                    anchors[si] = (addr, text)
                else:
                    pending.append((addr, si))
            if text:
                self.formulas[addr] = "=" + text.lstrip("=")
        for addr, si in pending:
            if si not in anchors:
                raise ValueError(f"Shared formula anchor missing: {addr}, si={si}")
            source, formula = anchors[si]
            self.formulas[addr] = "=" + translate_formula(formula, source, addr).lstrip("=")

    def raw_value(self, addr: str) -> Any:
        addr = normalize_ref(addr)
        if addr in self.overrides: return self.overrides[addr]
        cell = self.cells.get(addr)
        if cell is None: return None
        kind = cell.attrib.get("t")
        if kind == "inlineStr":
            return "".join(node.text or "" for node in cell.iter(Q("t")))
        value = cell.find(Q("v"))
        if value is None or value.text is None: return None
        if kind == "s": return self.shared_strings[int(value.text)]
        if kind in ("str", "e"): return value.text
        try: return float(value.text)
        except ValueError: return value.text

    def value(self, addr: str) -> Any:
        addr = normalize_ref(addr)
        if addr in self.overrides: return self.overrides[addr]
        if addr in self.cache: return self.cache[addr]
        formula = self.formulas.get(addr)
        if not formula: return self.raw_value(addr)
        if addr in self.stack: raise FormulaError(f"Circular reference at {addr}")
        self.stack.add(addr)
        try:
            result = evaluate(formula, self.value, self.range_value)
        except (FormulaError, ZeroDivisionError, TypeError, ValueError):
            result = self.raw_value(addr)
        finally:
            self.stack.remove(addr)
        self.cache[addr] = result
        return result

    def range_value(self, start: str, end: str) -> RangeValue:
        match1 = re.fullmatch(r"([A-Z]+)(\d+)", start)
        match2 = re.fullmatch(r"([A-Z]+)(\d+)", end)
        if not match1 or not match2: raise FormulaError(f"Invalid range {start}:{end}")
        c1, r1, c2, r2 = col_number(match1.group(1)), int(match1.group(2)), col_number(match2.group(1)), int(match2.group(2))
        cells = [f"{col_name(col)}{row}" for row in range(min(r1,r2), max(r1,r2)+1) for col in range(min(c1,c2), max(c1,c2)+1)]
        return RangeValue(cells, [self.value(cell) for cell in cells])

    def set_input(self, addr: str, value: float, source: str, reason: str = "", allow_formula: bool = False) -> None:
        addr = normalize_ref(addr)
        old = self.value(addr)
        has_formula = addr in self.formulas
        if has_formula and not allow_formula:
            raise ValueError(f"Protected formula cell cannot be overwritten: {addr}")
        self.overrides[addr] = float(value or 0)
        if has_formula:
            self.formulas.pop(addr, None)
        self.cache.clear()
        self.log.append(ChangeLog(addr, old, float(value or 0), source, reason, has_formula))

    def set_text(self, addr: str, value: str, source: str, reason: str = "", allow_formula: bool = False) -> None:
        addr = normalize_ref(addr)
        old = self.value(addr)
        has_formula = addr in self.formulas
        if has_formula and not allow_formula:
            raise ValueError(f"Protected formula cell cannot be overwritten: {addr}")
        text = str(value)
        self.overrides[addr] = text
        if has_formula:
            self.formulas.pop(addr, None)
        self.cache.clear()
        self.log.append(ChangeLog(addr, old, text, source, reason, has_formula))

    def recalculate(self) -> dict[str, str]:
        self.cache.clear()
        errors: dict[str, str] = {}
        for addr in self.formulas:
            try: self.value(addr)
            except Exception as exc: errors[addr] = str(exc)
        return errors

    def formula_changes(self) -> list[str]:
        return sorted(addr for addr in self.original_formulas if addr not in self.formulas)

    @staticmethod
    def _values_differ(old_value: Any, new_value: Any) -> bool:
        if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
            return abs(float(old_value) - float(new_value)) > 1e-9
        return old_value != new_value

    def _direct_input_changes(self) -> set[str]:
        direct_prefixes = ("sales.", "production.", "mcm.", "raw_material.")
        direct_sources = {
            "manufacturing_adjustment",
            "sga_adjustment",
            "cogs.goods",
            "cogs.customs_refund",
            "cogs.disposal",
            "cogs.obsolescence",
        }
        return {
            item.cell
            for item in self.log
            if (
                item.source.startswith(direct_prefixes)
                or item.source in direct_sources
            )
            and self._values_differ(item.old_value, item.new_value)
        }

    def _direct_input_logs(self) -> list[ChangeLog]:
        changed_cells = self._direct_input_changes()
        return [item for item in self.log if item.cell in changed_cells]

    def audit_entry_count(self) -> int:
        """Return the number of existing trace rows in a downloaded workbook."""
        existing = self._worksheet_target(self.entries, AUDIT_SHEET_NAME)
        if existing is None:
            return 0
        audit_root = ET.fromstring(self.entries[existing[0]])
        sheet_data = audit_root.find(Q("sheetData"))
        if sheet_data is None:
            return 0
        return max(0, len(sheet_data.findall(Q("row"))) - 1)

    def restore_audit_logs(self, records: list[dict[str, Any]] | None) -> None:
        """Restore direct-input logs when downloading a result made by an older session."""
        for record in records or []:
            required = {"cell", "old_value", "new_value", "source"}
            if not required.issubset(record):
                continue
            self.log.append(
                ChangeLog(
                    cell=str(record["cell"]),
                    old_value=record.get("old_value"),
                    new_value=record.get("new_value"),
                    source=str(record["source"]),
                    reason=str(record.get("reason", "")),
                    formula_overwritten=bool(record.get("formula_overwritten", False)),
                )
            )

    @staticmethod
    def _audit_category(source: str) -> str:
        if source.startswith("sales."):
            return "판매"
        if source.startswith("production."):
            return "생산"
        if source.startswith("mcm."):
            return "MCM(유상사급)"
        if source.startswith("raw_material.purchase_estimate."):
            return "원재료 투입비"
        if source == "manufacturing_adjustment":
            return "제조경비"
        if source == "sga_adjustment":
            return "판관비"
        return "매출원가"

    def _row_label(self, row: int) -> str:
        for column in ("D", "C", "B", "A"):
            value = self.raw_value(f"{column}{row}")
            if value not in (None, ""):
                return str(value).strip()
        return f"{row}행"

    def _audit_item(self, item: ChangeLog) -> str:
        source = item.source
        parts = source.split(".")
        if source.startswith("sales.") and len(parts) >= 3:
            suffix = {
                "quantity": "수량",
                "amount": "매출액",
                "manufactured_quantity": "제조 수량",
                "manufactured_amount": "제조 매출액",
                "goods_quantity": "상품 수량",
                "goods_amount": "상품 매출액",
            }.get(parts[-1], parts[-1])
            product = {
                "new_business": "신사업",
                "other": "기타매출",
            }.get(parts[1], parts[1])
            return f"{product} {suffix}"
        if source.startswith("production.") and len(parts) >= 2:
            return f"{parts[1]} 생산수량"
        if source.startswith("mcm.") and len(parts) >= 2:
            return f"{parts[1]} 수량"
        if source == "raw_material.purchase_estimate.front_process":
            return "구매팀 예상 투입비_전공정"
        if source == "raw_material.purchase_estimate.back_process":
            return "구매팀 예상 투입비_후공정"
        if source == "cogs.disposal":
            return "제품 폐기손실"
        if source == "cogs.obsolescence":
            return "제품 진부화 평가손실"
        if source == "cogs.customs_refund":
            return "원재료 관세 환급금"
        if source == "cogs.goods":
            return "상품 매출원가"
        if source == "sga_adjustment":
            row = int(re.search(r"\d+", item.cell).group(0))
            prefix = "판매비" if row <= 1147 else "일반관리비"
            return f"{prefix}_{self._row_label(row)}"
        row = int(re.search(r"\d+", item.cell).group(0))
        return self._row_label(row)

    @staticmethod
    def _audit_month(cell: str) -> int | None:
        match = re.fullmatch(r"([A-Z]+)\d+", cell)
        if not match:
            return None
        month = col_number(match.group(1)) - col_number("E") + 1
        return month if 1 <= month <= 12 else None

    @staticmethod
    def _append_inline_cell(row: ET.Element, address: str, value: Any) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            cell = ET.SubElement(row, Q("c"), {"r": address})
            ET.SubElement(cell, Q("v")).text = repr(float(value))
            return
        cell = ET.SubElement(row, Q("c"), {"r": address, "t": "inlineStr"})
        inline = ET.SubElement(cell, Q("is"))
        text = ET.SubElement(inline, Q("t"))
        text.text = "" if value is None else str(value)

    @staticmethod
    def _worksheet_target(entries: dict[str, bytes], sheet_name: str) -> tuple[str, ET.Element, ET.Element] | None:
        workbook = ET.fromstring(entries["xl/workbook.xml"])
        sheets = workbook.find(Q("sheets"))
        if sheets is None:
            return None
        sheet = next((node for node in sheets.findall(Q("sheet")) if node.attrib.get("name") == sheet_name), None)
        if sheet is None:
            return None
        relationship_id = sheet.attrib.get(f"{{{OFFICE_REL_NS}}}id")
        relationships = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
        relationship = next(
            (
                node for node in relationships.findall(f"{{{REL_NS}}}Relationship")
                if node.attrib.get("Id") == relationship_id
            ),
            None,
        )
        if relationship is None:
            return None
        target = relationship.attrib["Target"].replace("\\", "/")
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = f"xl/{target}"
        return path, workbook, relationships

    @staticmethod
    def _new_audit_sheet(entries: dict[str, bytes]) -> tuple[str, ET.Element]:
        workbook_name = "xl/workbook.xml"
        rels_name = "xl/_rels/workbook.xml.rels"
        workbook = ET.fromstring(entries[workbook_name])
        relationships = ET.fromstring(entries[rels_name])
        sheets = workbook.find(Q("sheets"))
        if sheets is None:
            sheets = ET.SubElement(workbook, Q("sheets"))

        existing_targets = {
            node.attrib.get("Target", "")
            for node in relationships.findall(f"{{{REL_NS}}}Relationship")
        }
        sheet_number = 1
        while f"worksheets/sheet{sheet_number}.xml" in existing_targets:
            sheet_number += 1
        target = f"worksheets/sheet{sheet_number}.xml"
        sheet_path = f"xl/{target}"

        existing_rids = {
            node.attrib.get("Id", "")
            for node in relationships.findall(f"{{{REL_NS}}}Relationship")
        }
        rid_number = 1
        while f"rId{rid_number}" in existing_rids:
            rid_number += 1
        relationship_id = f"rId{rid_number}"
        ET.SubElement(
            relationships,
            f"{{{REL_NS}}}Relationship",
            {
                "Id": relationship_id,
                "Type": f"{OFFICE_REL_NS}/worksheet",
                "Target": target,
            },
        )

        sheet_ids = [int(node.attrib.get("sheetId", "0")) for node in sheets.findall(Q("sheet"))]
        new_sheet = ET.Element(
            Q("sheet"),
            {
                "name": AUDIT_SHEET_NAME,
                "sheetId": str(max(sheet_ids, default=0) + 1),
                f"{{{OFFICE_REL_NS}}}id": relationship_id,
            },
        )
        children = list(sheets)
        data_index = next((index for index, node in enumerate(children) if node.attrib.get("name") == "Data"), len(children) - 1)
        sheets.insert(max(data_index + 1, 0), new_sheet)

        content_types_name = "[Content_Types].xml"
        content_types = ET.fromstring(entries[content_types_name])
        ET.SubElement(
            content_types,
            f"{{{CONTENT_TYPES_NS}}}Override",
            {
                "PartName": f"/{sheet_path}",
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            },
        )
        entries[workbook_name] = serialize_xml(workbook, ("x15", "xr", "xr6", "xr10", "xr2"))
        entries[rels_name] = serialize_xml(relationships, default_namespace=REL_NS)
        entries[content_types_name] = serialize_xml(content_types, default_namespace=CONTENT_TYPES_NS)

        root = ET.Element(Q("worksheet"))
        views = ET.SubElement(root, Q("sheetViews"))
        view = ET.SubElement(views, Q("sheetView"), {"workbookViewId": "0"})
        ET.SubElement(view, Q("pane"), {"ySplit": "1", "topLeftCell": "A2", "activePane": "bottomLeft", "state": "frozen"})
        ET.SubElement(root, Q("sheetFormatPr"), {"defaultRowHeight": "15"})
        columns = ET.SubElement(root, Q("cols"))
        for index, width in enumerate((7, 9, 18, 28, 13, 17, 17, 17, 62, 10), start=1):
            ET.SubElement(columns, Q("col"), {"min": str(index), "max": str(index), "width": str(width), "customWidth": "1"})
        sheet_data = ET.SubElement(root, Q("sheetData"))
        header = ET.SubElement(sheet_data, Q("row"), {"r": "1"})
        for index, value in enumerate(("번호", "월", "구분", "항목", "반영 셀", "기준값", "입력값", "차이", "사유", "셀 이동"), start=1):
            GoldenWorkbook._append_inline_cell(header, f"{col_name(index)}1", value)
        ET.SubElement(root, Q("autoFilter"), {"ref": "A1:J1"})
        ET.SubElement(root, Q("hyperlinks"))
        return sheet_path, root

    def _append_audit_sheet(self, entries: dict[str, bytes]) -> None:
        direct_logs = self._direct_input_logs()
        existing = self._worksheet_target(entries, AUDIT_SHEET_NAME)
        if existing is None:
            sheet_path, audit_root = self._new_audit_sheet(entries)
        else:
            sheet_path = existing[0]
            audit_root = ET.fromstring(entries[sheet_path])
        if not direct_logs:
            entries[sheet_path] = serialize_xml(audit_root)
            return

        sheet_data = audit_root.find(Q("sheetData"))
        if sheet_data is None:
            sheet_data = ET.SubElement(audit_root, Q("sheetData"))
        existing_rows = [int(row.attrib.get("r", "0")) for row in sheet_data.findall(Q("row"))]
        next_row = max(existing_rows, default=1) + 1
        hyperlinks = audit_root.find(Q("hyperlinks"))
        if hyperlinks is None:
            hyperlinks = ET.SubElement(audit_root, Q("hyperlinks"))

        for item in direct_logs:
            row = ET.SubElement(sheet_data, Q("row"), {"r": str(next_row)})
            month = self._audit_month(item.cell)
            delta = (
                float(item.new_value) - float(item.old_value)
                if isinstance(item.old_value, (int, float)) and isinstance(item.new_value, (int, float))
                else ""
            )
            values = (
                next_row - 1,
                f"{month}월" if month else "",
                self._audit_category(item.source),
                self._audit_item(item),
                item.cell,
                item.old_value,
                item.new_value,
                delta,
                item.reason,
                "이동",
            )
            for index, value in enumerate(values, start=1):
                self._append_inline_cell(row, f"{col_name(index)}{next_row}", value)
            ET.SubElement(
                hyperlinks,
                Q("hyperlink"),
                {
                    "ref": f"J{next_row}",
                    "location": f"'Data'!{item.cell}",
                    "display": "이동",
                },
            )
            next_row += 1

        auto_filter = audit_root.find(Q("autoFilter"))
        if auto_filter is None:
            auto_filter = ET.SubElement(audit_root, Q("autoFilter"))
        auto_filter.attrib["ref"] = f"A1:J{next_row - 1}"
        entries[sheet_path] = serialize_xml(audit_root)

    def save(self, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.recalculate()
        # If an input replaces the anchor of a shared formula, detach only that
        # shared group. Other formulas and cached values remain byte-equivalent
        # in meaning to the Golden Model, which is the most Excel-compatible
        # way to preserve a complex workbook.
        impacted_shared: set[str] = set()
        for addr in self.overrides:
            cell = self.cells.get(addr)
            f = cell.find(Q("f")) if cell is not None else None
            if f is not None and f.attrib.get("t") == "shared" and f.attrib.get("si") and (f.text or "").strip():
                impacted_shared.add(f.attrib["si"])

        for addr, cell in self.cells.items():
            f = cell.find(Q("f"))
            if f is None or f.attrib.get("si") not in impacted_shared or addr in self.overrides:
                continue
            f.attrib.clear()
            f.text = self.formulas[addr].lstrip("=")

        for addr, value in self.overrides.items():
            cell = self.cells.get(addr)
            if cell is None:
                row_num = re.search(r"\d+", addr).group(0)
                sheet_data = self.root.find(Q("sheetData"))
                row = next((r for r in sheet_data.findall(Q("row")) if r.attrib.get("r") == row_num), None)
                if row is None:
                    row = ET.SubElement(sheet_data, Q("row"), {"r": row_num})
                cell = ET.SubElement(row, Q("c"), {"r": addr})
                self.cells[addr] = cell
            for child in list(cell):
                if child.tag in (Q("f"), Q("v"), Q("is")): cell.remove(child)
            if isinstance(value, str):
                cell.attrib["t"] = "inlineStr"
                inline = ET.SubElement(cell, Q("is"))
                ET.SubElement(inline, Q("t")).text = value
            else:
                cell.attrib.pop("t", None)
                ET.SubElement(cell, Q("v")).text = repr(float(value))
        entries = dict(self.entries)
        entries[self.sheet_xml] = serialize_xml(self.root, ("x14ac", "xr", "xr2", "xr3"))
        self._append_audit_sheet(entries)
        if self._worksheet_target(entries, AUDIT_SHEET_NAME) is None:
            raise RuntimeError("입력반영내역 시트를 생성하지 못했습니다.")
        workbook_name = "xl/workbook.xml"
        wb = ET.fromstring(entries[workbook_name])
        calc = wb.find(Q("calcPr"))
        if calc is None: calc = ET.SubElement(wb, Q("calcPr"))
        calc.attrib.update({"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"})
        entries[workbook_name] = serialize_xml(wb, ("x15", "xr", "xr6", "xr10", "xr2"))
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items(): archive.writestr(name, data)
        return destination

    def log_dicts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.log]
