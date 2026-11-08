"""Genera evidencias SINTÉTICAS de un run del gate con el formato real (CSV del orquestador 3.4.0 → loadtest.json).

Salidas:
  app/src/demo/*.json       modo demo de la Fabric App (VITE_DEMO_MODE=true)
  docs/ejemplo-informe.md   informe de ejemplo

Uso:  python tools/make_demo_evidence.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from conftest import write_run  # noqa: E402  (mismo generador de CSV que los tests)

from promotion_gate.config import load_config  # noqa: E402
from promotion_gate.loadtest import read_runs, summarize  # noqa: E402
from promotion_gate.report import render_markdown  # noqa: E402
from promotion_gate.verdict import decide  # noqa: E402

ITEM_ID = "11111111-2222-3333-4444-555555555555"
RUN_ID = "demo-20261104-101500"
START = 1_793_000_000.0  # 2026-10-26T07:33:20Z

REVIEW = {
    "dataset": "Ventas", "item_id": ITEM_ID, "workspace": "Ventas [Test]",
    "findings": [
        {"rule": "Do not use floating point data types", "category": "Performance", "severity": "Warning",
         "object_type": "Column", "object_name": "'Hechos'[Importe]", "description": "",
         "url": "https://learn.microsoft.com/power-bi/connect-data/desktop-data-types"},
        {"rule": "Do not use floating point data types", "category": "Performance", "severity": "Warning",
         "object_type": "Column", "object_name": "'Hechos'[Coste]", "description": "", "url": ""},
        {"rule": "Use the DIVIDE function for division", "category": "DAX Expressions", "severity": "Warning",
         "object_type": "Measure", "object_name": "Margen %", "description": "", "url": ""},
        {"rule": "Set IsAvailableInMdx to false on non-attribute columns", "category": "Performance",
         "severity": "Warning", "object_type": "Column", "object_name": "'Hechos'[IdTransaccion]", "description": "",
         "url": ""},
        {"rule": "Provide format string for measures", "category": "Formatting", "severity": "Info",
         "object_type": "Measure", "object_name": "Ventas", "description": "Las medidas visibles deberían tener formato.",
         "url": ""},
    ],
    "vertipaq": {"model_size_mb": 3200.0, "top_columns": [
        {"table": "Hechos", "column": "IdTransaccion", "size_mb": 1100.0, "pct_of_model": 34.4,
         "cardinality": 48000000, "data_type": "String"},
        {"table": "Hechos", "column": "FechaHora", "size_mb": 420.0, "pct_of_model": 13.1, "cardinality": 9000000,
         "data_type": "DateTime"},
        {"table": "Hechos", "column": "Importe", "size_mb": 310.0, "pct_of_model": 9.7, "cardinality": 2100000,
         "data_type": "Double"},
        {"table": "Cliente", "column": "Email", "size_mb": 140.0, "pct_of_model": 4.4, "cardinality": 850000,
         "data_type": "String"},
    ], "top_tables": [{"table": "Hechos", "rows": 48000000, "size_mb": 2600.0},
                      {"table": "Cliente", "rows": 850000, "size_mb": 380.0}]},
}

CAPACITY = {
    "version": "v53", "capacity_id": "0f0f0f0f-1111-2222-3333-444444444444", "timepoints_in_window": 42,
    "covers_window_end": True, "peak_utilization_pct": 86.4, "avg_utilization_pct": 51.0,
    "peak_interactive_delay_pct": 92.0, "peak_interactive_rejection_pct": 12.0, "peak_background_rejection_pct": 3.0,
    "peak_carryover_pct": 4.0,
    "model": {"item_id": ITEM_ID, "found": True, "cu_s": 5400.0, "failed_operations": 3, "rejected_operations": 0,
              "throttling_min": 1.5, "operations": [
                  {"operation": "Query", "cu_s": 5100.0, "duration_s": 2900.0, "operations": 2280, "failed": 3,
                   "rejected": 0, "throttling_min": 1.5, "cu_s_per_operation": 2.237},
                  {"operation": "Dataset On-Demand Refresh", "cu_s": 300.0, "duration_s": 600.0, "operations": 1,
                   "failed": 0, "rejected": 0, "throttling_min": 0.0, "cu_s_per_operation": 300.0}]},
    "tooling": {"workspace_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "cu_s": 900.0, "share_pct": 7.5},
}


# Versión corregida del modelo: sin Double ni columna de texto pesada, menos memoria y la capacidad holgada.
REVIEW_FIXED = {
    **REVIEW,
    "findings": [f for f in REVIEW["findings"] if f["rule"] not in (
        "Do not use floating point data types", "Set IsAvailableInMdx to false on non-attribute columns")],
    "vertipaq": {"model_size_mb": 1850.0, "top_columns": [
        {"table": "Hechos", "column": "FechaHora", "size_mb": 300.0, "pct_of_model": 16.2, "cardinality": 9000000,
         "data_type": "DateTime"},
        {"table": "Hechos", "column": "IdTransaccion", "size_mb": 190.0, "pct_of_model": 10.3,
         "cardinality": 48000000, "data_type": "Int64"},
        {"table": "Hechos", "column": "Importe", "size_mb": 120.0, "pct_of_model": 6.5, "cardinality": 2100000,
         "data_type": "Decimal"},
        {"table": "Cliente", "column": "Email", "size_mb": 140.0, "pct_of_model": 7.6, "cardinality": 850000,
         "data_type": "String"},
    ], "top_tables": [{"table": "Hechos", "rows": 48000000, "size_mb": 1300.0},
                      {"table": "Cliente", "rows": 850000, "size_mb": 380.0}]},
}

CAPACITY_FIXED = {
    **CAPACITY, "peak_utilization_pct": 62.5, "avg_utilization_pct": 38.0, "peak_interactive_delay_pct": 41.0,
    "peak_interactive_rejection_pct": 4.0, "peak_background_rejection_pct": 0.5, "peak_carryover_pct": 0.0,
    "model": {"item_id": ITEM_ID, "found": True, "cu_s": 3100.0, "failed_operations": 0, "rejected_operations": 0,
              "throttling_min": 0.0, "operations": [
                  {"operation": "Query", "cu_s": 2800.0, "duration_s": 1500.0, "operations": 2340, "failed": 0,
                   "rejected": 0, "throttling_min": 0.0, "cu_s_per_operation": 1.197},
                  {"operation": "Dataset On-Demand Refresh", "cu_s": 300.0, "duration_s": 420.0, "operations": 1,
                   "failed": 0, "rejected": 0, "throttling_min": 0.0, "cu_s_per_operation": 300.0}]},
    "tooling": {"workspace_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "cu_s": 640.0, "share_pct": 6.1},
}


def build(run_id: str = RUN_ID, fixed: bool = False, start: float = START) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        logs = Path(tmp) / "logs"
        prefix = f"gate-{run_id}"
        if fixed:
            write_run(logs, prefix, "ventas", 6, start, slowdown=0.6, ts="20261105-100000")
            write_run(logs, prefix, "ventas", 20, start + 100, slowdown=0.75, ts="20261105-100500")
            write_run(logs, prefix, "ventas", 60, start + 300, slowdown=1.1, ts="20261105-101500")
        else:
            write_run(logs, prefix, "ventas", 6, start, ts="20261104-100000")
            write_run(logs, prefix, "ventas", 20, start + 100, slowdown=2.0, ts="20261104-100500")
            write_run(logs, prefix, "ventas", 60, start + 300, slowdown=4.5, failed_query_every=37, failed_users=2,
                      ts="20261104-101500")
        summary = summarize(read_runs(logs, prefix), slow_query_sec=5.0)
    summary["run_prefix"] = f"gate-{run_id}"
    review = REVIEW_FIXED if fixed else REVIEW
    capacity = dict(CAPACITY_FIXED if fixed else CAPACITY, window=summary["window"])
    cfg = load_config(ROOT / "config" / "gate.yaml")
    verdict = decide(review, summary, capacity, cfg,
                     {"run_id": run_id, "dataset": "Ventas", "item_id": ITEM_ID, "requested_by": "equipo-bi",
                      "source_ref": "fabric-app"})
    return {"model_review": review, "loadtest": summary, "capacity": capacity, "verdict": verdict}


def _write(ev: dict, folder: Path) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in ev.items():
        (folder / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n",
                                             encoding="utf-8")
    md = render_markdown(ev["verdict"], ev["model_review"], ev["loadtest"], ev["capacity"])
    (folder / "report.md").write_text(md, encoding="utf-8")
    return md


def main() -> None:
    demo = ROOT / "app" / "src" / "demo"
    for stale in demo.glob("*.json"):
        stale.unlink()
    (demo / "report.md").unlink(missing_ok=True)
    fail = build()
    md = _write(fail, demo / "fail")
    passed = build("demo-20261105-101500", fixed=True, start=START + 86_400)
    _write(passed, demo / "pass")
    (ROOT / "docs" / "ejemplo-informe.md").write_text(
        "> Ejemplo generado con datos sintéticos (`python tools/make_demo_evidence.py`). No es un run real.\n\n" + md,
        encoding="utf-8")
    print(f"fail={fail['verdict']['verdict']} pass={passed['verdict']['verdict']} "
          f"(promocionable {passed['verdict']['promotable']}): {demo}")


if __name__ == "__main__":
    main()
