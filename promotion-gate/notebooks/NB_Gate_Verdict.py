# %% [markdown]
# # NB_Gate_Verdict
# Paso 4 del gate: combina model_review.json, loadtest.json y capacity.json, decide PASS, WARN o FAIL,
# escribe `verdict.json` y `report.md` en `Files/PromotionGate/runs/<run_id>/` y añade el resultado a las tablas
# Delta `gate_runs` y `gate_checks` (histórico auditable de promociones).

# %%
import sys
sys.path.insert(0, "{{GATE_WHEEL}}")  # wheel puro: se importa sin %pip, que las sesiones de alta concurrencia no admiten

# %% [parameters]
run_id = "manual"
dataset = ""
requested_by = ""
source_ref = ""
gate_config = ""

# %%
import json
import os

from promotion_gate.config import load_config
from promotion_gate.report import render_markdown
from promotion_gate.verdict import decide

GATE_ROOT = "/lakehouse/default/Files/PromotionGate"
cfg = load_config(f"{GATE_ROOT}/config/gate.yaml", override=gate_config)
out_dir = f"{GATE_ROOT}/runs/{run_id}"
os.makedirs(out_dir, exist_ok=True)


def _load(name):
    path = f"{out_dir}/{name}"
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


review, load_summary, capacity = _load("model_review.json"), _load("loadtest.json"), _load("capacity.json")
context = {"run_id": run_id, "dataset": dataset or (review or {}).get("dataset"), "requested_by": requested_by,
           "source_ref": source_ref, "item_id": (review or {}).get("item_id")}
verdict = decide(review, load_summary, capacity, cfg, context)
report = render_markdown(verdict, review, load_summary, capacity)

with open(f"{out_dir}/verdict.json", "w", encoding="utf-8") as fh:
    json.dump(verdict, fh, ensure_ascii=False, indent=1, default=str)
with open(f"{out_dir}/report.md", "w", encoding="utf-8") as fh:
    fh.write(report)

# %%
from pyspark.sql.types import BooleanType, StringType, StructField, StructType

RUNS = StructType([StructField(n, BooleanType() if n == "promotable" else StringType()) for n in (
    "run_id", "dataset", "item_id", "verdict", "promotable", "evaluated_utc", "requested_by", "source_ref", "areas",
    "report_path")])
CHECKS = StructType([StructField(n, StringType()) for n in ("run_id", "check_id", "area", "status", "title", "detail")])
try:
    spark.createDataFrame([(
        str(run_id), context["dataset"] or "", context["item_id"] or "", verdict["verdict"], bool(verdict["promotable"]),
        verdict["evaluated_utc"], requested_by or "", source_ref or "", json.dumps(verdict["areas"]),
        f"Files/PromotionGate/runs/{run_id}/report.md")], RUNS) \
        .write.mode("append").option("mergeSchema", "true").saveAsTable("gate_runs")
    spark.createDataFrame([(str(run_id), c["id"], c["area"], c["status"], c["title"], c["detail"] or "")
                           for c in verdict["checks"]], CHECKS) \
        .write.mode("append").option("mergeSchema", "true").saveAsTable("gate_checks")
except Exception as exc:  # la auditoría no debe impedir que el pipeline reciba el veredicto
    print(f"No se pudo escribir gate_runs/gate_checks: {type(exc).__name__}: {exc}")

print(report)
notebookutils.notebook.exit(json.dumps({
    "stage": "verdict", "verdict": verdict["verdict"], "promotable": verdict["promotable"],
    "report": f"Files/PromotionGate/runs/{run_id}/report.md",
}))
