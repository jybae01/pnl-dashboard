from __future__ import annotations

import multiprocessing
import os
import queue
import threading
from pathlib import Path
from typing import Any, Mapping

from .preflight import ExcelPreflightValidator, PreflightValidationError
from .workbook import extract_period_types


class IsolatedParserError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IsolatedExcelPreflight:
    """Run untrusted XLSX parsing outside the BFF process with a hard deadline.

    Linux applies address-space and CPU limits. Windows still gets process crash
    containment and wall timeout, but has no stdlib-enforced memory limit.
    """

    _slots = threading.BoundedSemaphore(2)

    def __init__(self, mapping: Mapping[str, Any], *, timeout_seconds: int = 30,
                 memory_limit_bytes: int = 1024 * 1024 * 1024,
                 worker_target=None) -> None:
        if not 1 <= timeout_seconds <= 300:
            raise ValueError("parser timeout must be 1-300 seconds")
        if not 256 * 1024 * 1024 <= memory_limit_bytes <= 4 * 1024 * 1024 * 1024:
            raise ValueError("parser memory limit must be 256MiB-4GiB")
        self._mapping = dict(mapping)
        self._timeout = timeout_seconds
        self._memory_limit = memory_limit_bytes
        self._worker_target = worker_target or _parse_worker

    def require_with_metadata(self, path: str | Path, *, expected_year: int,
                              file_name: str | None = None) -> Mapping[str, str]:
        if not self._slots.acquire(blocking=False):
            raise IsolatedParserError("workbook_parser_busy")
        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue(maxsize=1)
        process = context.Process(
            target=self._worker_target,
            args=(str(Path(path).resolve()), file_name or Path(path).name, self._mapping, expected_year,
                  self._memory_limit, result_queue),
            name="pnl-xlsx-preflight",
        )
        started = False
        try:
            process.start()
            started = True
            process.join(self._timeout)
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join()
                raise IsolatedParserError("workbook_resource_timeout")
            result = result_queue.get(timeout=2)
        except queue.Empty as exc:
            raise IsolatedParserError("workbook_parser_crashed") from exc
        except IsolatedParserError:
            raise
        except Exception as exc:
            raise IsolatedParserError("workbook_parser_crashed") from exc
        finally:
            if started and process.is_alive():
                process.kill()
                process.join()
            result_queue.close()
            result_queue.join_thread()
            if started:
                process.close()
            self._slots.release()
        if result.get("status") != "ok":
            raise IsolatedParserError(str(result.get("code") or "workbook_validation_failed"))
        value = result.get("period_types")
        if not isinstance(value, dict):
            raise IsolatedParserError("workbook_parser_contract_invalid")
        return {str(key): str(item) for key, item in value.items()}


def _parse_worker(path: str, file_name: str, mapping: Mapping[str, Any], expected_year: int,
                  memory_limit_bytes: int, result_queue) -> None:
    try:
        if os.name == "posix":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        from .bff.model_ingestion import _validate_xlsx_package
        _validate_xlsx_package(Path(path), file_name)
        validator = ExcelPreflightValidator(mapping)
        validator.require(path, expected_year=expected_year)
        result_queue.put({"status": "ok", "period_types": extract_period_types(path)})
    except PreflightValidationError as exc:
        issues = ",".join(item.code for item in exc.report.issues)[:500]
        result_queue.put({"status": "error", "code": issues or "workbook_validation_failed"})
    except MemoryError:
        result_queue.put({"status": "error", "code": "workbook_resource_limit"})
    except BaseException:
        result_queue.put({"status": "error", "code": "workbook_parser_failed"})
