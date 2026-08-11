from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .engine import ForecastEngine, ForecastInput
from .temp_artifacts import TempArtifactPolicy


@dataclass(frozen=True)
class ForecastBenchmarkResult:
    fixture_class: str
    months: int
    wall_seconds: float
    peak_python_bytes: int
    input_bytes: int
    output_bytes: int
    peak_temp_bytes: int


def benchmark_forecast(source: Path, mapping: Path, *, months: int,
                       fixture_class: str = "synthetic_or_fixture",
                       runner: Callable[[Path, Path, int, Path], None] | None = None,
                       temp_policy: TempArtifactPolicy | None = None) -> ForecastBenchmarkResult:
    if months not in {1, 6, 12}:
        raise ValueError("benchmark months must be 1, 6, or 12")
    source = source.resolve(); mapping = mapping.resolve()
    run = runner or _run_engine
    if temp_policy is not None:
        temp_policy.ensure_capacity(source.stat().st_size * (months + 2))
    with tempfile.TemporaryDirectory(
        prefix="pnl-forecast-benchmark-",
        dir=temp_policy.root if temp_policy is not None else None,
    ) as directory:
        root = Path(directory)
        tracemalloc.start()
        started = time.perf_counter()
        run(source, mapping, months, root)
        wall = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        output = root / "forecast.xlsx"
        peak_temp = sum(item.stat().st_size for item in root.rglob("*") if item.is_file())
        return ForecastBenchmarkResult(
            fixture_class=fixture_class, months=months, wall_seconds=wall,
            peak_python_bytes=peak, input_bytes=source.stat().st_size,
            output_bytes=output.stat().st_size, peak_temp_bytes=peak_temp,
        )


def _run_engine(source: Path, mapping: Path, months: int, root: Path) -> None:
    current = root / "base.xlsx"
    shutil.copyfile(source, current)
    for index in range(1, months + 1):
        target = root / ("forecast.xlsx" if index == months else f"month-{index}.xlsx")
        ForecastEngine(current, mapping).run(ForecastInput(month=index), target)
        current = target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m forecast.benchmark")
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--mapping", default="config/model_mapping.json")
    parser.add_argument("--fixture-class", default="synthetic_or_fixture",
                        choices=("synthetic_or_fixture", "private_company_workbook"))
    parser.add_argument("--temp-root", required=True,
                        help="production-like benchmark temp volume")
    parser.add_argument("--temp-quota-bytes", type=int, default=2 * 1024**3)
    args = parser.parse_args(argv)
    policy = TempArtifactPolicy(Path(args.temp_root), args.temp_quota_bytes)
    results = [benchmark_forecast(Path(args.workbook), Path(args.mapping), months=value,
                                  fixture_class=args.fixture_class, temp_policy=policy)
               for value in (1, 6, 12)]
    print(json.dumps([asdict(value) for value in results], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
