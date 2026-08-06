"""Forecast V1 calculation and Golden Model adapter."""

from .engine import ForecastEngine, ForecastInput, ForecastResult
from .analysis_export_hook import install_analysis_export_hook

install_analysis_export_hook()

__all__ = ["ForecastEngine", "ForecastInput", "ForecastResult"]
