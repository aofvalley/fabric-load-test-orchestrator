"""Tipos comunes: un Check es una comprobación con estado PASS, WARN, FAIL o SKIP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_RANK = {PASS: 0, SKIP: 1, WARN: 2, FAIL: 3}


@dataclass
class Check:
    id: str
    area: str  # model_review | load_test | capacity
    status: str
    title: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Advice:
    area: str
    priority: int  # 1 = alta, 2 = media, 3 = baja
    title: str
    action: str
    evidence: str = ""
    reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def n(value: Any, digits: int | None = None) -> str:
    """Número en formato español (coma decimal). Sin `digits`: enteros sin decimales y el resto con hasta dos."""
    if value is None:
        return "–"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits is None:
        if x.is_integer():
            return str(int(x))
        text = f"{x:.2f}".rstrip("0").rstrip(".")
    else:
        text = f"{x:.{digits}f}"
    return text.replace(".", ",")


def pc(rate: float, digits: int = 1) -> str:
    """Fracción (0..1) como porcentaje en español: 0.023 -> '2,3 %'."""
    return f"{n(rate * 100, digits)} %"


def worst(statuses: list[str]) -> str:
    if not statuses:
        return SKIP
    return max(statuses, key=lambda s: _RANK[s])


def percentile(values: list[float], pct: float) -> float:
    """Percentil con interpolación lineal (igual que numpy por defecto). pct en 0..100."""
    if not values:
        return float("nan")
    data = sorted(values)
    if len(data) == 1:
        return float(data[0])
    k = (len(data) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(data) - 1)
    return float(data[lo] + (data[hi] - data[lo]) * (k - lo))
