# %% [markdown]
# # NB_Gate_CapacityMetrics
# Paso 3 del gate: consulta el modelo semántico de la app Fabric Capacity Metrics para la ventana del test
# (utilización, throttling, carry-over, CU y operaciones fallidas del modelo y CU del propio generador de carga).
# Las consultas son las de FUAM (microsoft/fabric-toolbox) con detección de versión (v40 a v53).
# La identidad necesita acceso de lectura al workspace de la app de Capacity Metrics.

# %%
import sys
sys.path.insert(0, "{{GATE_WHEEL}}")  # wheel puro: se importa sin %pip, que las sesiones de alta concurrencia no admiten

# %% [parameters]
run_id = "manual"
capacity_metrics_workspace = ""
capacity_metrics_dataset = "Fabric Capacity Metrics"
capacity_id = ""
model_item_id = ""
model_workspace = ""
tooling_workspace_id = ""
margin_minutes = 5
max_extra_wait_minutes = 20   # sondeo cada 2 min hasta que Capacity Metrics cubra el final del test
gate_config = ""

# %%
import json
import os
import time
from datetime import datetime, timedelta, timezone

import sempy.fabric as fabric

from promotion_gate.capacity import (SUPPORTED_VERSIONS, UTC_OFFSET_QUERY, analyze, days_in_window, detect_version,
                                     evaluate_capacity, item_operation_hour_query, item_operation_query,
                                     normalize_rows, parse_utc_offset,
                                     timepoint_utc, timepoints_query, to_dt)
from promotion_gate.checks import worst
from promotion_gate.config import load_config

GATE_ROOT = "/lakehouse/default/Files/PromotionGate"
cfg = load_config(f"{GATE_ROOT}/config/gate.yaml", override=gate_config)
out_dir = f"{GATE_ROOT}/runs/{run_id}"
os.makedirs(out_dir, exist_ok=True)


def _load(name):
    path = f"{out_dir}/{name}"
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def evaluate(dax):
    return fabric.evaluate_dax(dataset=capacity_metrics_dataset, workspace=capacity_metrics_workspace or None, dax_string=dax)


metrics = {}
try:
    window = (_load("loadtest.json").get("window") or {})
    if not window.get("start_utc"):
        raise ValueError("loadtest.json no tiene ventana: el test de carga no dejó resultados")
    item_id = model_item_id or _load("model_review.json").get("item_id")
    if not item_id:
        raise ValueError("Falta model_item_id y model_review.json no lo trae")
    cap = capacity_id
    if not cap:
        ws_id = fabric.resolve_workspace_id(model_workspace.strip() or None)
        cap = str(fabric.list_workspaces(filter=f"id eq '{ws_id}'").iloc[0]["Capacity Id"])
    tooling = tooling_workspace_id or notebookutils.runtime.context.get("currentWorkspaceId")

    version = detect_version(evaluate)
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"Capacity Metrics {version} no soportada: actualiza la app")

    try:  # los timepoints van en la hora local de la instalación de la app
        offset = parse_utc_offset(evaluate(UTC_OFFSET_QUERY).to_dict("records"))
    except Exception:  # noqa: BLE001 - versiones sin 'Latest Summary Timestamp'
        offset = 0.0
    print(f"Capacity Metrics {version}, timepoints en UTC{offset:+g}")

    deadline = time.time() + 60 * int(max_extra_wait_minutes)
    end = to_dt(window["end_utc"])
    local = lambda key: to_dt(window[key]) + timedelta(hours=offset)
    while True:
        tps = []
        for day in days_in_window(window["start_utc"], window["end_utc"], offset):
            tps += evaluate(timepoints_query(version, cap, day)).to_dict("records")
        latest = max((timepoint_utc(r.get("TimePoint"), offset) for r in normalize_rows(tps) if r.get("TimePoint") is not None),
                     default=None)
        if (latest and latest >= end) or time.time() > deadline:
            break
        print(f"Capacity Metrics llega hasta {latest}; el test terminó a las {end}. Reintento en 2 min.")
        time.sleep(120)

    # Operaciones por item: en v53, solo las horas del test (tabla horaria); antes, el día completo.
    scope = "hour" if version == "v53" else "day"
    if scope == "hour":
        ios = evaluate(item_operation_hour_query(version, cap, local("start_utc"), local("end_utc"))).to_dict("records")
    else:
        ios = []
        for day in days_in_window(window["start_utc"], window["end_utc"], offset):
            ios += evaluate(item_operation_query(version, cap, day)).to_dict("records")

    metrics = analyze(tps, ios, window, item_id, tooling, margin_min=int(margin_minutes), version=version, capacity_id=cap,
                      utc_offset_hours=offset, operations_scope=scope)
except Exception as exc:
    metrics = {"error": f"{type(exc).__name__}: {exc}"}

metrics["extracted_utc"] = datetime.now(timezone.utc).isoformat()
with open(f"{out_dir}/capacity.json", "w", encoding="utf-8") as fh:
    json.dump(metrics, fh, ensure_ascii=False, indent=1, default=str)

checks = evaluate_capacity(metrics, cfg)
for c in checks:
    print(f"{c.status:5} {c.title}: {c.detail}")

notebookutils.notebook.exit(json.dumps({
    "stage": "capacity", "status": worst([c.status for c in checks]), "error": metrics.get("error"),
    "peak_utilization_pct": metrics.get("peak_utilization_pct"),
}))
