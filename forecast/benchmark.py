from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import tempfile
import threading
import time
import tracemalloc
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from .engine import ForecastEngine, ForecastInput
from .preflight import ExcelPreflightValidator
from .temp_artifacts import TempArtifactPolicy
from .workbook import extract_period_types


@dataclass(frozen=True)
class BenchmarkRunMetrics:
    month_wall_seconds: tuple[float, ...]
    peak_temp_bytes: int


@dataclass(frozen=True)
class ForecastBenchmarkResult:
    fixture_class: str
    months: int
    start_month: int
    end_month: int
    wall_seconds: float
    month_wall_seconds: tuple[float, ...]
    peak_python_bytes: int | None
    peak_process_rss_bytes: int | None
    rss_sampling_interval_seconds: float
    input_bytes: int
    output_bytes: int
    peak_temp_bytes: int
    output_ooxml_package_valid: bool
    output_preflight_passed: bool | None
    expected_month_state_passed: bool | None
    source_unchanged: bool
    cleanup_succeeded: bool


Runner = Callable[[Path, Path, int, int, Path], BenchmarkRunMetrics | None]
LegacyRunner = Callable[[Path, Path, int, Path], BenchmarkRunMetrics | None]
RSS_SAMPLING_INTERVAL_SECONDS = 0.01


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_bytes(root: Path) -> int:
    return sum(item.stat().st_size for item in root.rglob("*") if item.is_file())


def _is_valid_ooxml_package(path: Path) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"}
            if not required.issubset(names) or archive.testzip() is not None:
                return False
            roots = {
                name: ET.fromstring(archive.read(name))
                for name in required
            }
            return (
                roots["[Content_Types].xml"].tag.endswith("}Types")
                and roots["_rels/.rels"].tag.endswith("}Relationships")
                and roots["xl/workbook.xml"].tag.endswith("}workbook")
            )
    except (ET.ParseError, KeyError, OSError, zipfile.BadZipFile, RuntimeError):
        return False


def _process_rss_bytes() -> int | None:
    """Return current RSS using only the standard library when supported."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = (
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            )
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            process = kernel32.GetCurrentProcess()
            ok = psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb
            )
            return int(counters.WorkingSetSize) if ok else None
        except (AttributeError, OSError, ValueError):
            return None
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
        return resident_pages * page_size
    except (AttributeError, IndexError, OSError, ValueError):
        return None


class _PeakRssSampler:
    def __init__(self, interval_seconds: float = RSS_SAMPLING_INTERVAL_SECONDS):
        self.interval_seconds = interval_seconds
        self.peak: int | None = _process_rss_bytes()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            value = _process_rss_bytes()
            if value is not None:
                self.peak = value if self.peak is None else max(self.peak, value)

    def start(self) -> None:
        self._thread.start()

    def finish(self) -> int | None:
        self._stop.set()
        self._thread.join()
        value = _process_rss_bytes()
        if value is not None:
            self.peak = value if self.peak is None else max(self.peak, value)
        return self.peak


def _call_runner(run: Runner | LegacyRunner, source: Path, mapping: Path,
                 start_month: int, months: int, root: Path) -> BenchmarkRunMetrics | None:
    parameters = tuple(inspect.signature(run).parameters.values())
    positional = tuple(
        value for value in parameters
        if value.kind in (value.POSITIONAL_ONLY, value.POSITIONAL_OR_KEYWORD)
    )
    if any(value.kind == value.VAR_POSITIONAL for value in parameters) or len(positional) >= 5:
        return run(source, mapping, start_month, months, root)
    if len(positional) == 4:
        if start_month != 1:
            raise ValueError("legacy benchmark runner supports only start_month=1")
        return run(source, mapping, months, root)
    raise TypeError("benchmark runner must accept 4 legacy or 5 window arguments")


def benchmark_forecast(source: Path, mapping: Path, *, months: int,
                       start_month: int = 1,
                       fixture_class: str = "synthetic_or_fixture",
                       runner: Runner | LegacyRunner | None = None,
                       temp_policy: TempArtifactPolicy | None = None) -> ForecastBenchmarkResult:
    if isinstance(months, bool) or not isinstance(months, int) or months not in {1, 6, 12}:
        raise ValueError("benchmark months must be 1, 6, or 12")
    if isinstance(start_month, bool) or not isinstance(start_month, int):
        raise ValueError("benchmark start_month must be an integer from 1..12")
    if start_month < 1 or start_month > 12:
        raise ValueError("benchmark start_month must be 1..12")
    end_month = start_month + months - 1
    if end_month > 12:
        raise ValueError("benchmark window must remain within months 1..12")
    source = source.resolve(); mapping = mapping.resolve()
    source_hash = _sha256(source)
    run = runner if runner is not None else _run_engine
    uses_engine = runner is None
    if temp_policy is not None:
        temp_policy.ensure_capacity(source.stat().st_size * (months + 2))
    root: Path | None = None
    result_values: dict[str, object]
    with tempfile.TemporaryDirectory(
        prefix="pnl-forecast-benchmark-",
        dir=temp_policy.root if temp_policy is not None else None,
    ) as directory:
        root = Path(directory)
        owns_tracemalloc = not tracemalloc.is_tracing()
        if owns_tracemalloc:
            tracemalloc.start()
        rss = _PeakRssSampler()
        rss.start()
        started = time.perf_counter()
        try:
            run_metrics = _call_runner(run, source, mapping, start_month, months, root)
            wall = time.perf_counter() - started
            peak_python = tracemalloc.get_traced_memory()[1] if owns_tracemalloc else None
        finally:
            peak_process_rss = rss.finish()
            if owns_tracemalloc:
                tracemalloc.stop()
        output = root / "forecast.xlsx"
        peak_temp = max(
            run_metrics.peak_temp_bytes if run_metrics is not None else 0,
            _tree_bytes(root),
        )
        valid_xlsx = _is_valid_ooxml_package(output)
        preflight_passed: bool | None = None
        month_state_passed: bool | None = None
        if uses_engine and valid_xlsx:
            mapping_snapshot = root / "mapping.json"
            mapping_data = json.loads(mapping_snapshot.read_text(encoding="utf-8"))
            preflight_report = ExcelPreflightValidator(mapping_data).validate(output)
            preflight_passed = preflight_report.passed
            if preflight_passed:
                source_periods = extract_period_types(source)
                expected_periods = dict(source_periods)
                for month in range(start_month, end_month + 1):
                    expected_periods[str(month)] = "추정"
                month_state_passed = preflight_report.period_types == expected_periods
            else:
                month_state_passed = False
        result_values = {
            "fixture_class": fixture_class,
            "months": months,
            "start_month": start_month,
            "end_month": end_month,
            "wall_seconds": wall,
            "month_wall_seconds": (
                run_metrics.month_wall_seconds if run_metrics is not None else ()
            ),
            "peak_python_bytes": peak_python,
            "peak_process_rss_bytes": peak_process_rss,
            "rss_sampling_interval_seconds": RSS_SAMPLING_INTERVAL_SECONDS,
            "input_bytes": source.stat().st_size,
            "output_bytes": output.stat().st_size,
            "peak_temp_bytes": peak_temp,
            "output_ooxml_package_valid": valid_xlsx,
            "output_preflight_passed": preflight_passed,
            "expected_month_state_passed": month_state_passed,
            "source_unchanged": _sha256(source) == source_hash,
        }
    return ForecastBenchmarkResult(
        **result_values,
        cleanup_succeeded=root is not None and not root.exists(),
    )


def _run_engine(source: Path, mapping: Path, start_month: int, months: int,
                root: Path) -> BenchmarkRunMetrics:
    mapping_snapshot = root / "mapping.json"
    shutil.copyfile(mapping, mapping_snapshot)
    current = root / "base.xlsx"
    shutil.copyfile(source, current)
    peak_temp = _tree_bytes(root)
    month_times: list[float] = []
    for offset in range(months):
        month = start_month + offset
        target = root / (
            "forecast.xlsx" if offset == months - 1 else f"month-{month}.xlsx"
        )
        started = time.perf_counter()
        ForecastEngine(current, mapping_snapshot).run(ForecastInput(month=month), target)
        month_times.append(time.perf_counter() - started)
        peak_temp = max(peak_temp, _tree_bytes(root))
        current.unlink()
        current = target
    return BenchmarkRunMetrics(tuple(month_times), peak_temp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m forecast.benchmark")
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--mapping", default="config/model_mapping.json")
    parser.add_argument("--fixture-class", default="synthetic_or_fixture",
                        choices=("synthetic_or_fixture", "private_company_workbook"))
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--months", type=int, nargs="+", choices=(1, 6, 12),
                        default=(1, 6, 12))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--temp-root", required=True,
                        help="production-like benchmark temp volume")
    parser.add_argument("--temp-quota-bytes", type=int, default=2 * 1024**3)
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.start_month < 1 or args.start_month > 12:
        parser.error("--start-month must be 1..12")
    invalid_windows = [
        months for months in args.months
        if args.start_month + months - 1 > 12
    ]
    if invalid_windows:
        parser.error(
            "requested benchmark window exceeds December; pass an explicit "
            "--months list that fits the selected --start-month"
        )
    policy = TempArtifactPolicy(Path(args.temp_root), args.temp_quota_bytes)
    results: list[dict[str, object]] = []
    for months in args.months:
        for run_index in range(1, args.repeats + 1):
            result = asdict(benchmark_forecast(
                Path(args.workbook), Path(args.mapping), months=months,
                start_month=args.start_month, fixture_class=args.fixture_class,
                temp_policy=policy,
            ))
            result["run_index"] = run_index
            results.append(result)
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
