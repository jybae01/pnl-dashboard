from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def normalize_account(value: str) -> str:
    return "".join(str(value or "").replace("_", "").split()).lower()


@dataclass(frozen=True)
class AnalysisConfig:
    product_groups: tuple[str, ...]
    variable_manufacturing_accounts: frozenset[str]
    variable_sga_accounts: frozenset[str]
    transport_accounts: frozenset[str]
    absolute_tolerance: float = 1.0
    relative_tolerance: float = 1e-9

    @classmethod
    def load(cls, path: str | Path) -> "AnalysisConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            product_groups=tuple(payload["product_groups"]),
            variable_manufacturing_accounts=frozenset(
                normalize_account(item) for item in payload["manufacturing"]["variable_accounts"]
            ),
            variable_sga_accounts=frozenset(
                normalize_account(item) for item in payload["sga"]["variable_accounts"]
            ),
            transport_accounts=frozenset(
                normalize_account(item) for item in payload["sga"]["transport_accounts"]
            ),
            absolute_tolerance=float(payload["reconciliation"]["absolute_tolerance"]),
            relative_tolerance=float(payload["reconciliation"]["relative_tolerance"]),
        )

    def is_variable_manufacturing(self, account: str) -> bool:
        return normalize_account(account) in self.variable_manufacturing_accounts

    def is_variable_sga(self, account: str) -> bool:
        return normalize_account(account) in self.variable_sga_accounts

    def is_transport(self, account: str) -> bool:
        return normalize_account(account) in self.transport_accounts
