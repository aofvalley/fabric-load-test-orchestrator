# %% [markdown]
# # NB_Gate_ModelReview
# Paso 1 del gate de promoción: Best Practice Analyzer (semantic-link-labs) y estadísticas VertiPaq del modelo.
# Escribe `Files/PromotionGate/runs/<run_id>/model_review.json` y sale con un JSON corto para el pipeline.
# Necesita permiso de escritura (Contributor) sobre el workspace del modelo: BPA y VertiPaq leen el TOM.

# %%
import sys
sys.path.insert(0, "{{GATE_WHEEL}}")  # wheel puro: se importa sin %pip, que las sesiones de alta concurrencia no admiten
import importlib.util, subprocess
if importlib.util.find_spec("sempy_labs") is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "semantic-link-labs"])

# %% [parameters]
run_id = "manual"
dataset = ""
model_workspace = ""
gate_config = ""

# %%
import json
import os
from datetime import datetime, timezone

import sempy.fabric as fabric

from promotion_gate.bpa import (columns_from_sempy, evaluate_model_review, normalize_findings, summarize_vertipaq,
                                tables_from_sempy, warmup_queries)
from promotion_gate.checks import worst
from promotion_gate.config import load_config

GATE_ROOT = "/lakehouse/default/Files/PromotionGate"
cfg = load_config(f"{GATE_ROOT}/config/gate.yaml", override=gate_config)
out_dir = f"{GATE_ROOT}/runs/{run_id}"
os.makedirs(out_dir, exist_ok=True)
ws = model_workspace.strip() or None

review = {"dataset": dataset, "workspace": ws, "started_utc": datetime.now(timezone.utc).isoformat()}
try:
    if not dataset.strip():
        raise ValueError("El parámetro dataset es obligatorio")
    review["item_id"] = fabric.resolve_dataset_id(dataset, workspace=ws)
    review["workspace_id"] = fabric.resolve_workspace_id(ws)

    import sempy_labs as labs

    bpa = labs.run_model_bpa(dataset=dataset, workspace=ws, return_dataframe=True)
    review["findings"] = normalize_findings(bpa.reset_index().to_dict("records"))

    def vertipaq():
        tables = tables_from_sempy(fabric.list_tables(dataset=dataset, workspace=ws, extended=True).to_dict("records"))
        cols_df = fabric.list_columns(dataset=dataset, workspace=ws, extended=True)
        review["vertipaq_source_columns"] = [str(x) for x in cols_df.columns]  # diagnóstico: nombres que devuelve sempy
        return tables, columns_from_sempy(cols_df.to_dict("records"))

    tables, columns = vertipaq()
    total = sum(t["size_bytes"] for t in tables) or None
    if not total:  # Direct Lake frío: se calientan las columnas como haría el primer usuario y se mide de nuevo
        for dax in warmup_queries(columns):
            fabric.evaluate_dax(dataset=dataset, workspace=ws, dax_string=dax)
        tables, columns = vertipaq()
        total = sum(t["size_bytes"] for t in tables) or None
        review["vertipaq_warmed_up"] = True
    review["vertipaq"] = summarize_vertipaq(total, columns, tables)
except Exception as exc:  # el veredicto lo convierte en FAIL con este mensaje
    review["error"] = f"{type(exc).__name__}: {exc}"

with open(f"{out_dir}/model_review.json", "w", encoding="utf-8") as fh:
    json.dump(review, fh, ensure_ascii=False, indent=1, default=str)

checks = evaluate_model_review(review, cfg)
for c in checks:
    print(f"{c.status:5} {c.title}: {c.detail}")

notebookutils.notebook.exit(json.dumps({
    "stage": "model_review", "status": worst([c.status for c in checks]),
    "item_id": review.get("item_id"), "findings": len(review.get("findings", [])), "error": review.get("error"),
}))
