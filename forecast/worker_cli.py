from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
from pathlib import Path

from .persistence.factory import create_repository_bundle
from .worker import WorkerJobControl
from .worker_runtime import DeterministicComparisonExecutor, WorkerRunner


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Independent P&L calculation queue worker (no Streamlit session runtime)."
    )
    command.add_argument("--backend", choices=("local", "supabase"), default="local")
    command.add_argument("--data-directory", type=Path, default=Path("data"))
    command.add_argument("--mapping", type=Path, default=Path("config/model_mapping.json"))
    command.add_argument(
        "--worker-id",
        default=os.getenv("PNL_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}",
    )
    command.add_argument("--lease-seconds", type=int, default=300)
    command.add_argument("--poll-seconds", type=float, default=2.0)
    command.add_argument("--once", action="store_true")
    command.add_argument("--max-jobs", type=int)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    bundle = create_repository_bundle(args.data_directory, backend=args.backend)
    control = WorkerJobControl(bundle.jobs, args.worker_id)
    executor = DeterministicComparisonExecutor(
        bundle.models,
        args.mapping,
        allow_legacy_local_inputs=(bundle.backend == "local"),
    )
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(signal_name, request_stop)
        except (AttributeError, ValueError):
            pass

    runner = WorkerRunner(
        control,
        executor,
        lease_seconds=args.lease_seconds,
        poll_seconds=args.poll_seconds,
        stop_event=stop,
    )
    if args.once:
        runner.run_once()
        return 0
    runner.run_forever(max_jobs=args.max_jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
