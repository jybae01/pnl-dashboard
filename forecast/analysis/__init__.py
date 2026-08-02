"""Plan/actual/forecast variance analysis engine.

The package is intentionally independent from Streamlit and the Forecast writer.
"""

from .engine import AnalysisEngine, AnalysisResult
from .schema import (
    ActivityRecord,
    AnalysisScenario,
    DirectEffectRecord,
    ExpenseRecord,
    PnlRecord,
    ProductRecord,
    ScenarioMeta,
)

__all__ = [
    "ActivityRecord",
    "AnalysisEngine",
    "AnalysisResult",
    "AnalysisScenario",
    "DirectEffectRecord",
    "ExpenseRecord",
    "PnlRecord",
    "ProductRecord",
    "ScenarioMeta",
]
