from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read_code(environment_name: str, prompt: str) -> str:
    configured = os.getenv(environment_name, "").strip()
    if configured:
        return configured
    return getpass.getpass(prompt).strip()


def main() -> int:
    viewer_code = read_code("VIEWER_CODE", "Viewer access code: ")
    admin_code = read_code("ADMIN_CODE", "Admin access code: ")

    if not viewer_code or not admin_code:
        print("Both access codes are required.")
        return 1
    if viewer_code == admin_code:
        print("Viewer and admin access codes must be different.")
        return 1

    try:
        from streamlit.web import cli as streamlit_cli
    except ModuleNotFoundError:
        print("Required packages are not installed.")
        print("Run this command once in the project folder:")
        print("python -m pip install -r requirements.txt")
        return 1

    os.environ["VIEWER_CODE"] = viewer_code
    os.environ["ADMIN_CODE"] = admin_code
    port = os.getenv("FORECAST_PORT", "8501")
    sys.argv = [
        "streamlit",
        "run",
        str(ROOT / "app.py"),
        "--server.port",
        port,
    ]
    return int(streamlit_cli.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
