"""Veredicto del gate: combina las comprobaciones de las tres áreas."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .advisor import build_advice
from .bpa import evaluate_model_review
from .capacity import evaluate_capacity
from .checks import FAIL, PASS, SKIP, WARN, Check, worst
from .loadtest import evaluate_load_test

AREAS = ("model_review", "load_test", "capacity")


def decide(review: dict[str, Any] | None, load_summary: dict[str, Any] | None, capacity: dict[str, Any] | None,
           cfg: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    review_checks = evaluate_model_review(review, cfg)
    if not load_summary and not capacity and worst([c.status for c in review_checks]) == FAIL:
        # Con stop_on_review_fail el pipeline no lanza la carga: esas fases quedan omitidas, no suspendidas.
        why = "La revisión del modelo no es apta y el gate se detuvo antes del test de carga (stop_on_review_fail)."
        checks = review_checks + [
            Check("load_test.skipped", "load_test", SKIP, "Test de carga omitido", why),
            Check("capacity.skipped", "capacity", SKIP, "Capacity Metrics omitido", why),
        ]
    else:
        checks = review_checks + evaluate_load_test(load_summary, cfg) + evaluate_capacity(capacity, cfg)
    by_area = {a: worst([c.status for c in checks if c.area == a]) for a in AREAS}
    overall = worst([c.status for c in checks])
    if overall not in (FAIL, WARN):
        overall = PASS
    promotable = overall == PASS or (overall == WARN and not cfg["verdict"]["warn_blocks_promotion"])
    advice = build_advice(review, load_summary, capacity, cfg)
    return {
        "gate_version": __version__,
        "evaluated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "context": context or {},
        "verdict": overall,
        "promotable": promotable,
        "areas": by_area,
        "counts": dict(Counter(c.status for c in checks)),
        "checks": [c.to_dict() for c in checks],
        "advice": [a.to_dict() for a in advice],
        "config": cfg,
    }
