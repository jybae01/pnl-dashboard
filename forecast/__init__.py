"""Forecast V1 calculation and Golden Model adapter."""

from .engine import ForecastEngine, ForecastInput, ForecastResult


def _install_analysis_export_hook_if_available() -> None:
    """Install the Streamlit-only export hook without coupling core imports to UI.

    Forecast calculation and analysis modules are also imported by unit tests,
    command-line tooling, and workbook adapters where Streamlit is intentionally
    not installed. The hook remains active for the Streamlit app because the
    app imports Streamlit before importing this package.
    """
    try:
        import streamlit  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name != "streamlit":
            raise
        return

    from .analysis_export_hook import install_analysis_export_hook

    install_analysis_export_hook()


_install_analysis_export_hook_if_available()

__all__ = ["ForecastEngine", "ForecastInput", "ForecastResult"]
