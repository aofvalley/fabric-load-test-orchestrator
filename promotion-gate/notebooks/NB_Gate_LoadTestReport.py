# %% [markdown]
# # NB_Gate_LoadTestReport
# Paso 2 del gate: lee los CSV que el Fabric Load Test Orchestrator dejó en `Files/PerfScenarios/logs/<run_prefix>-*`
# y calcula, por modelo y nivel de la rampa, percentiles, consultas fallidas, rendimiento y visuales lentas.
# Escribe `Files/PromotionGate/runs/<run_id>/loadtest.json`. El lakehouse por defecto debe ser el del orquestador.

# %%
import sys
sys.path.insert(0, "{{GATE_WHEEL}}")  # wheel puro: se importa sin %pip, que las sesiones de alta concurrencia no admiten

# %% [parameters]
run_id = "manual"
run_prefix = ""
logs_root = "/lakehouse/default/Files/PerfScenarios/logs"
gate_config = ""

# %%
import json
import os

from promotion_gate.checks import worst
from promotion_gate.config import load_config
from promotion_gate.loadtest import evaluate_load_test, read_runs, summarize

GATE_ROOT = "/lakehouse/default/Files/PromotionGate"
cfg = load_config(f"{GATE_ROOT}/config/gate.yaml", override=gate_config)
out_dir = f"{GATE_ROOT}/runs/{run_id}"
os.makedirs(out_dir, exist_ok=True)
prefix = run_prefix or f"gate-{run_id}"

try:
    summary = summarize(read_runs(logs_root, prefix), slow_query_sec=cfg["load_test"]["slow_query_sec"])
    summary["run_prefix"] = prefix
except Exception as exc:
    summary = {"run_prefix": prefix, "models": [], "error": f"{type(exc).__name__}: {exc}"}

with open(f"{out_dir}/loadtest.json", "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=1, default=str)

checks = evaluate_load_test(summary, cfg)
for c in checks:
    print(f"{c.status:5} {c.title}: {c.detail}")
for m in summary.get("models", []):
    for lv in m["levels"]:
        print(f"{m['model_key']:>20} c{lv['level']:<4} queries={lv['queries']:<6} failed={lv['failed_queries']:<4} "
              f"p50={lv['p50']} p95={lv['p95']} qps={lv['qps']}")

notebookutils.notebook.exit(json.dumps({
    "stage": "load_test", "status": worst([c.status for c in checks]), "window": summary.get("window"),
    "models": len(summary.get("models", [])),
}))
