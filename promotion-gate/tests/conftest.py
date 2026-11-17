import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Columnas exactas que escribe RunPerfScenario_v3 del Fabric Load Test Orchestrator (v3.4.0; sin status ni error en v3.2.0)
ORCHESTRATOR_COLUMNS = [
    "loadtest_id", "model", "concurrent_threads", "iterations", "delay_sec", "query_number", "visual_name", "visual_id",
    "iteration", "query", "rows", "duration", "start_time", "start_time_dt", "customdata", "effective_username",
    "thread_id", "action_index", "source_label", "original_think_time_sec", "scaled_think_time_sec",
    "applied_think_time_sec", "status", "error",
]

VISUALS = [("Ventas por mes", 0.4), ("Top clientes", 0.8), ("Matriz detalle", 2.0)]


def write_run(logs: Path, prefix: str, model_key: str, level: int, t0: float, slowdown: float = 1.0,
              failed_users: int = 0, ts: str = "20261104-100000", model: str = "Ventas",
              failed_query_every: int = 0, legacy: bool = False) -> Path:
    run_id = f"{prefix}-{model_key}-c{level}-{ts}"
    folder = logs / run_id
    folder.mkdir(parents=True)
    for user in range(level - failed_users):
        rows = []
        t = t0 + user * 0.5
        for qn, (visual, base) in enumerate(VISUALS, start=1):
            dur = base * (slowdown if visual == "Matriz detalle" else 1.0) * (1 + user * 0.01)
            failed = bool(failed_query_every) and (user * len(VISUALS) + qn) % failed_query_every == 0
            rows.append({
                "loadtest_id": run_id, "model": model, "concurrent_threads": level, "iterations": 1, "delay_sec": 4,
                "query_number": qn, "visual_name": visual, "visual_id": f"v{qn}", "iteration": 0,
                "query": f'EVALUATE\n  SUMMARIZECOLUMNS(\'Fecha\'[Mes], "x", [Ventas {qn}])', "rows": 12,
                "duration": round(dur, 4), "start_time": t, "start_time_dt": "2026-11-04 10:00:00",
                "customdata": "", "effective_username": "", "thread_id": user, "action_index": qn,
                "source_label": "UserAction", "original_think_time_sec": 0, "scaled_think_time_sec": 0,
                "applied_think_time_sec": 0,
                "status": "error" if failed else "ok",
                "error": "AdomdErrorResponseException: The operation was throttled; user ana@contoso.com" if failed else "",
            })
            if failed:
                rows[-1]["rows"], rows[-1]["duration"] = 0, 30.0
            if legacy:
                del rows[-1]["status"], rows[-1]["error"]
            t += dur + 1
        with (folder / f"{run_id}_user_{user}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ORCHESTRATOR_COLUMNS[:-2] if legacy else ORCHESTRATOR_COLUMNS)
            w.writeheader()
            w.writerows(rows)
    if failed_users:
        (folder / "error.log").write_text(
            "Data Source=powerbi://api.powerbi.com/v1.0/myorg/ws;Password=<redacted-token>;EffectiveUserName=ana@contoso.com"
            "  : The operation was throttled\n" * failed_users, encoding="utf-8")
    return folder


@pytest.fixture
def logs(tmp_path):
    root = tmp_path / "logs"
    write_run(root, "gate-r1", "ventas", 1, 1_793_000_000.0, ts="20261104-100000")
    write_run(root, "gate-r1", "ventas", 5, 1_793_000_100.0, slowdown=1.5, ts="20261104-100200")
    write_run(root, "gate-r1", "ventas", 10, 1_793_000_200.0, slowdown=4.0, ts="20261104-100400")
    write_run(root, "otro-run", "ventas", 3, 1_793_000_000.0, ts="20261104-090000")
    return root


@pytest.fixture
def review_ok():
    return {
        "dataset": "Ventas", "item_id": "11111111-2222-3333-4444-555555555555",
        "findings": [
            {"rule": "Use the DIVIDE function for division", "category": "DAX Expressions", "severity": "Warning",
             "object_type": "Measure", "object_name": "Margen", "description": "", "url": "https://example.org/divide"},
            {"rule": "Provide format string for measures", "category": "Formatting", "severity": "Info",
             "object_type": "Measure", "object_name": "Ventas", "description": "", "url": ""},
        ],
        "vertipaq": {"model_size_mb": 800.0, "top_columns": [
            {"table": "Hechos", "column": "Id", "size_mb": 100.0, "pct_of_model": 12.5, "cardinality": 1000000}],
            "top_tables": []},
    }


@pytest.fixture
def capacity_ok():
    return {
        "version": "v53", "timepoints_in_window": 40, "peak_utilization_pct": 55.0, "avg_utilization_pct": 30.0,
        "peak_interactive_delay_pct": 20.0, "peak_interactive_rejection_pct": 5.0, "peak_background_rejection_pct": 1.0,
        "peak_carryover_pct": 0.0,
        "model": {"item_id": "11111111-2222-3333-4444-555555555555", "found": True, "cu_s": 900.0,
                  "failed_operations": 0, "rejected_operations": 0, "throttling_min": 0.0,
                  "operations": [{"operation": "Query", "cu_s": 900.0, "duration_s": 300.0, "operations": 480,
                                  "failed": 0, "rejected": 0, "throttling_min": 0.0, "cu_s_per_operation": 1.875}]},
        "tooling": {"workspace_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "cu_s": 100.0, "share_pct": 5.0},
    }
