"""CLI `smgate`: evaluar en local, desplegar el gate en Fabric, lanzarlo, descargar el informe y promocionar.

Códigos de salida: 0 promocionable, 2 no promocionable, 1 error de uso o de plataforma.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_config
from .loadtest import read_runs, summarize
from .notebooks import bind_lakehouse, load_notebooks, notebook_definition
from .report import render_markdown
from .verdict import decide

ROOT = Path(__file__).resolve().parents[2]
GATE_FILES = "Files/PromotionGate"
NOTEBOOKS = ["NB_Gate_ModelReview", "NB_Gate_LoadTestReport", "NB_Gate_CapacityMetrics", "NB_Gate_Verdict"]
ORCHESTRATOR_PIPELINE = "PL_PerfTest_MultiModel_v3"
GATE_PIPELINE = "PL_PromotionGate"


def _json(path: str | None) -> Any:
    if not path:
        return None
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _exit_code(verdict: dict[str, Any]) -> int:
    return 0 if verdict.get("promotable") else 2


def cmd_evaluate(a: argparse.Namespace) -> int:
    cfg = load_config(a.config)
    review = _json(a.review)
    summary = _json(a.loadtest)
    if summary is None and a.logs:
        summary = summarize(read_runs(a.logs, a.run_prefix), slow_query_sec=cfg["load_test"]["slow_query_sec"])
    capacity = _json(a.capacity)
    verdict = decide(review, summary, capacity, cfg, {"run_id": a.run_id, "dataset": a.dataset})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    report = render_markdown(verdict, review, summary, capacity)
    (out / "report.md").write_text(report, encoding="utf-8")
    print(f"{verdict['verdict']} (promocionable: {verdict['promotable']}). Informe: {out / 'report.md'}")
    return _exit_code(verdict)


def _wheel(path: str | None) -> Path:
    if path:
        return Path(path)
    wheels = sorted((ROOT / "dist").glob("promotion_gate-*.whl"))
    if not wheels:
        raise SystemExit("No hay wheel en dist/: ejecuta  python -m pip wheel . -w dist --no-deps")
    return wheels[-1]


def render_notebooks(wheel_name: str) -> dict[str, dict[str, Any]]:
    nbs = load_notebooks(ROOT / "notebooks")
    missing = [n for n in NOTEBOOKS if n not in nbs]
    if missing:
        raise SystemExit(f"Faltan notebooks: {missing}")
    for nb in nbs.values():
        for cell in nb["cells"]:
            cell["source"] = [s.replace("{{GATE_WHEEL}}", f"/lakehouse/default/{GATE_FILES}/lib/{wheel_name}") for s in cell["source"]]
    return nbs


def cmd_build_notebooks(a: argparse.Namespace) -> int:
    nbs = render_notebooks(_wheel(a.wheel).name)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, nb in nbs.items():
        (out / f"{name}.ipynb").write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(nbs)} notebooks en {out}")
    return 0


def _client():
    from .fabric_api import FabricClient

    return FabricClient()


def cmd_deploy(a: argparse.Namespace) -> int:
    from .fabric_api import pipeline_definition

    fc = _client()
    wheel = _wheel(a.wheel)
    lh = fc.request("GET", f"workspaces/{a.workspace_id}/lakehouses/{a.lakehouse_id}")
    orch = fc.find_item(a.workspace_id, ORCHESTRATOR_PIPELINE, "DataPipeline")
    if not orch:
        raise SystemExit(f"No existe {ORCHESTRATOR_PIPELINE} en el workspace: instala antes el Fabric Load Test Orchestrator "
                         "en este mismo workspace y lakehouse (smgate install-orchestrator o deploy/deploy.ps1).")
    nbs = render_notebooks(wheel.name)
    plan = [f"subir {wheel.name} y gate.yaml a {GATE_FILES}/", *[f"notebook {n}" for n in NOTEBOOKS], f"pipeline {GATE_PIPELINE}"]
    print(f"Destino: workspace {a.workspace_id}, lakehouse {lh['displayName']}. Orquestador: {orch['id']}")
    print("Plan:\n  - " + "\n  - ".join(plan))
    if a.dry_run:
        print("DRY RUN: no se ha cambiado nada.")
        return 0
    fc.onelake_write(a.workspace_id, a.lakehouse_id, f"{GATE_FILES}/lib/{wheel.name}", wheel.read_bytes())
    fc.onelake_write(a.workspace_id, a.lakehouse_id, f"{GATE_FILES}/config/gate.yaml",
                     Path(a.config).read_bytes())
    ids = {"WORKSPACE_ID": a.workspace_id, f"PIPELINE:{ORCHESTRATOR_PIPELINE}": orch["id"]}
    for name in NOTEBOOKS:
        nb = bind_lakehouse(nbs[name], a.workspace_id, a.lakehouse_id, lh["displayName"])
        ids[f"NOTEBOOK:{name}"] = fc.upsert_item(a.workspace_id, name, "Notebook", notebook_definition(nb), a.overwrite,
                                                 "Gate de promoción de modelos semánticos")
        print(f"  notebook {name}: {ids[f'NOTEBOOK:{name}']}")
    raw = (ROOT / "pipelines" / f"{GATE_PIPELINE}.json").read_text(encoding="utf-8")
    pid = fc.upsert_item(a.workspace_id, GATE_PIPELINE, "DataPipeline", pipeline_definition(raw, ids), a.overwrite,
                         "Gate de promoción de modelos semánticos")
    print(f"  pipeline {GATE_PIPELINE}: {pid}\nOK")
    return 0


def _params(a: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = json.loads(Path(a.params_file).read_text(encoding="utf-8")) if a.params_file else {}
    for kv in a.param or []:
        k, _, v = kv.partition("=")
        try:
            params[k] = json.loads(v)
        except json.JSONDecodeError:
            params[k] = v
    return params


def coerce_to_pipeline_types(params: dict[str, Any]) -> dict[str, Any]:
    """Los parámetros String de PL_PromotionGate (p. ej. gate_config) viajan como texto aunque se escriban como JSON."""
    declared = json.loads((ROOT / "pipelines" / f"{GATE_PIPELINE}.json").read_text(encoding="utf-8"))["properties"]["parameters"]
    out = dict(params)
    for k, v in params.items():
        if declared.get(k, {}).get("type") == "String" and not isinstance(v, str):
            out[k] = json.dumps(v, ensure_ascii=False)
    return out

def cmd_run(a: argparse.Namespace) -> int:
    fc = _client()
    pipe = fc.find_item(a.workspace_id, GATE_PIPELINE, "DataPipeline")
    if not pipe:
        raise SystemExit(f"No existe {GATE_PIPELINE}: ejecuta  smgate deploy  primero.")
    params = coerce_to_pipeline_types(_params(a))
    if not params.get("dataset"):
        raise SystemExit("Falta el parámetro dataset (--param dataset=<modelo>)")
    params.setdefault("run_id", datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    location = fc.run_job(a.workspace_id, pipe["id"], "Pipeline", params)
    print(f"Gate lanzado: run {params['run_id']} (job {location.rstrip('/').split('/')[-1]})")
    if not a.wait:
        return 0
    last = {}

    def tick(job: dict) -> None:
        if job.get("status") != last.get("status"):
            print(f"  estado: {job.get('status')}")
            last["status"] = job.get("status")

    job = fc.wait_job(location, on_poll=tick)
    gate_run = params["run_id"]
    rc = cmd_fetch(argparse.Namespace(workspace_id=a.workspace_id, lakehouse_id=a.lakehouse_id, run_id=gate_run, out=a.out))
    if job.get("status") != "Completed" and rc == 0:
        print(f"El pipeline terminó en {job.get('status')}: {json.dumps(job.get('failureReason'))[:400]}")
        return 1
    return rc


def cmd_fetch(a: argparse.Namespace) -> int:
    fc = _client()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    found = {}
    for name in ("verdict.json", "report.md", "model_review.json", "loadtest.json", "capacity.json"):
        data = fc.onelake_read(a.workspace_id, a.lakehouse_id, f"{GATE_FILES}/runs/{a.run_id}/{name}")
        if data is not None:
            (out / name).write_bytes(data)
            found[name] = True
    if "verdict.json" not in found:
        print(f"No hay verdict.json para el run {a.run_id}: el gate no llegó al veredicto.")
        return 2
    verdict = json.loads((out / "verdict.json").read_text(encoding="utf-8"))
    print(f"{verdict['verdict']} (promocionable: {verdict['promotable']}). Informe: {out / 'report.md'}")
    return _exit_code(verdict)


def cmd_promote(a: argparse.Namespace) -> int:
    verdict = _json(a.verdict)
    if not verdict:
        raise SystemExit(f"No se puede leer {a.verdict}")
    if not verdict.get("promotable"):
        print(f"Promoción bloqueada: veredicto {verdict.get('verdict')}.")
        return 2
    item_id = a.item_id or verdict.get("context", {}).get("item_id")
    if not item_id:
        raise SystemExit("Falta --item-id y el veredicto no trae item_id")
    if verdict.get("context", {}).get("item_id") and verdict["context"]["item_id"].lower() != item_id.lower():
        raise SystemExit("El item del veredicto no coincide con --item-id: no se promociona otro modelo.")
    items = [{"sourceItemId": item_id, "itemType": "SemanticModel"}]
    items += [{"sourceItemId": r, "itemType": "Report"} for r in a.report_id or []]
    note = a.note or f"Gate {verdict['verdict']} run {verdict.get('context', {}).get('run_id')}"
    if a.dry_run:
        print(f"DRY RUN: desplegaría {items} de {a.source_stage_id} a {a.target_stage_id} con nota «{note}».")
        return 0
    _client().deploy_stage(a.deployment_pipeline_id, a.source_stage_id, a.target_stage_id, items, note)
    print("Promoción completada.")
    return 0


ORCH_NOTEBOOKS = ["RunPerfScenario_v3", "RunLoadTest_v3", "AnalyzeLoadTest_v3"]
ORCH_PIPELINES = ["PL_PerfTest_Ramp_v3", "PL_PerfTest_MultiModel_v3"]


def orchestrator_repo(explicit: str | None) -> Path:
    """Clon del Fabric Load Test Orchestrator: el indicado o, si el gate vive dentro de ese repo (promotion-gate/), su raíz."""
    repo = Path(explicit) if explicit else ROOT.parent
    if not (repo / "notebooks" / "RunLoadTest_v3.ipynb").exists():
        hint = "" if explicit else " El gate no está dentro del repo del orquestador: indica --repo <clon>."
        raise SystemExit(f"{repo} no es un clon de fabric-load-test-orchestrator (falta notebooks/RunLoadTest_v3.ipynb).{hint}")
    return repo


def cmd_install_orchestrator(a: argparse.Namespace) -> int:
    """Equivale a Setup_LoadTest_v3 del Fabric Load Test Orchestrator, pero desde fuera de Fabric (REST)."""
    from .fabric_api import pipeline_definition

    repo = orchestrator_repo(a.repo)
    fc = _client()
    lh = fc.request("GET", f"workspaces/{a.workspace_id}/lakehouses/{a.lakehouse_id}")
    print(f"Orquestador de {repo} en workspace {a.workspace_id}, lakehouse {lh['displayName']}")
    if a.dry_run:
        print("DRY RUN: " + ", ".join(ORCH_NOTEBOOKS + ORCH_PIPELINES))
        return 0
    ids = {"WORKSPACE_ID": a.workspace_id}
    for name in ORCH_NOTEBOOKS:
        nb = json.loads((repo / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))
        nb = bind_lakehouse(nb, a.workspace_id, a.lakehouse_id, lh["displayName"])
        ids[f"NOTEBOOK:{name}"] = fc.upsert_item(a.workspace_id, name, "Notebook", notebook_definition(nb), a.overwrite,
                                                 "Fabric Load Test Orchestrator")
        print(f"  notebook {name}: {ids[f'NOTEBOOK:{name}']}")
    for name in ORCH_PIPELINES:
        raw = (repo / "pipelines" / f"{name}.json").read_text(encoding="utf-8")
        ids[f"PIPELINE:{name}"] = fc.upsert_item(a.workspace_id, name, "DataPipeline", pipeline_definition(raw, ids),
                                                 a.overwrite, "Fabric Load Test Orchestrator")
        print(f"  pipeline {name}: {ids[f'PIPELINE:{name}']}")
    for folder in ("Files/PerfScenarios/Queries", "Files/PerfScenarios/logs"):
        fc.onelake_write(a.workspace_id, a.lakehouse_id, f"{folder}/.keep", b"")
    print("OK")
    return 0


def cmd_upload(a: argparse.Namespace) -> int:
    src = Path(a.file)
    dest = a.dest.rstrip("/") + "/" + src.name if a.dest.endswith("/") else a.dest
    if not dest.startswith("Files/"):
        raise SystemExit("--dest debe empezar por Files/ (p. ej. Files/PerfScenarios/Queries/)")
    if a.dry_run:
        print(f"DRY RUN: subiría {src} a {dest}")
        return 0
    _client().onelake_write(a.workspace_id, a.lakehouse_id, dest, src.read_bytes())
    print(f"Subido a {dest} (ruta en notebooks: /lakehouse/default/{dest})")
    return 0


def _typed(params: dict[str, Any]) -> dict[str, Any]:
    """Parámetros de RunNotebook: los objetos y listas (p. ej. gate_config) viajan como texto JSON."""
    kinds = {bool: "bool", int: "int", float: "float"}
    return {k: {"value": v if isinstance(v, (bool, int, float, str)) or v is None else json.dumps(v, ensure_ascii=False),
                "type": kinds.get(type(v), "string")} for k, v in params.items()}


def cmd_run_item(a: argparse.Namespace) -> int:
    """Lanza un notebook o pipeline concreto: repetir una fase del gate o lanzar solo el orquestador."""
    fc = _client()
    item_type = "Notebook" if a.name.startswith("NB_") else "DataPipeline"
    item = fc.find_item(a.workspace_id, a.name, item_type)
    if not item:
        raise SystemExit(f"No existe {item_type} {a.name} en el workspace")
    params = _params(a)
    if item_type == "Notebook":
        params.setdefault("_inlineInstallationEnabled", True)
        job_type, payload = "RunNotebook", _typed(params)
    else:
        job_type, payload = "Pipeline", params
    location = fc.run_job(a.workspace_id, item["id"], job_type, payload)
    print(f"{a.name} lanzado ({location.rstrip('/').split('/')[-1]})")
    if not a.wait:
        return 0
    job = fc.wait_job(location)
    print(f"{a.name}: {job.get('status')}" + (f" exitValue={job.get('exitValue')}" if job.get("exitValue") else ""))
    if job.get("failureReason"):
        print(json.dumps(job["failureReason"], ensure_ascii=False)[:800])
    return 0 if job.get("status") == "Completed" else 1


def cmd_capacity_dax(a: argparse.Namespace) -> int:
    from datetime import date as _date

    from .capacity import VERSION_PROBES, item_operation_query, timepoints_query

    if a.probes:
        for version, dax in VERSION_PROBES:
            print(f"-- sonda {version}\n{dax}\n")
        return 0
    day = _date.fromisoformat(a.date)
    print("-- Timepoints (30 s) de la capacidad\n" + timepoints_query(a.version, a.capacity_id, day))
    print("\n-- CU y operaciones por item y operación (día)\n" + item_operation_query(a.version, a.capacity_id, day))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="smgate", description="Gate de promoción de modelos semánticos (Fabric y Power BI)")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("evaluate", help="Veredicto e informe en local a partir de las evidencias")
    e.add_argument("--review", help="model_review.json")
    e.add_argument("--loadtest", help="loadtest.json ya resumido")
    e.add_argument("--logs", help="Carpeta PerfScenarios/logs descargada (alternativa a --loadtest)")
    e.add_argument("--run-prefix", default="ramp-v3")
    e.add_argument("--capacity", help="capacity.json")
    e.add_argument("--config", default=str(ROOT / "config" / "gate.yaml"))
    e.add_argument("--dataset", default="")
    e.add_argument("--run-id", default="local")
    e.add_argument("--out", default="out")
    e.set_defaults(func=cmd_evaluate)

    b = sub.add_parser("build-notebooks", help="Genera los .ipynb para importarlos a mano")
    b.add_argument("--wheel")
    b.add_argument("--out", default=str(ROOT / "dist" / "notebooks"))
    b.set_defaults(func=cmd_build_notebooks)

    d = sub.add_parser("deploy", help="Despliega notebooks, pipeline, wheel y umbrales en el workspace del orquestador")
    d.add_argument("--workspace-id", required=True)
    d.add_argument("--lakehouse-id", required=True)
    d.add_argument("--wheel")
    d.add_argument("--config", default=str(ROOT / "config" / "gate.yaml"))
    d.add_argument("--overwrite", action="store_true")
    d.add_argument("--dry-run", action="store_true")
    d.set_defaults(func=cmd_deploy)

    r = sub.add_parser("run", help="Lanza PL_PromotionGate y, con --wait, descarga el informe")
    r.add_argument("--workspace-id", required=True)
    r.add_argument("--lakehouse-id", required=True)
    r.add_argument("--params-file", help="JSON con los parámetros del pipeline")
    r.add_argument("--param", action="append", help="clave=valor (valor JSON o texto); se puede repetir")
    r.add_argument("--wait", action="store_true")
    r.add_argument("--out", default="out")
    r.set_defaults(func=cmd_run)

    f = sub.add_parser("fetch", help="Descarga verdict.json, report.md y evidencias de un run")
    f.add_argument("--workspace-id", required=True)
    f.add_argument("--lakehouse-id", required=True)
    f.add_argument("--run-id", required=True)
    f.add_argument("--out", default="out")
    f.set_defaults(func=cmd_fetch)

    m = sub.add_parser("promote", help="Promociona con deployment pipelines de Fabric solo si el veredicto lo permite")
    m.add_argument("--verdict", required=True)
    m.add_argument("--deployment-pipeline-id", required=True)
    m.add_argument("--source-stage-id", required=True)
    m.add_argument("--target-stage-id", required=True)
    m.add_argument("--item-id", help="Id del modelo en el stage origen (por defecto, el del veredicto)")
    m.add_argument("--report-id", action="append", help="Informes que acompañan al modelo")
    m.add_argument("--note")
    m.add_argument("--dry-run", action="store_true")
    m.set_defaults(func=cmd_promote)

    u = sub.add_parser("upload", help="Sube un fichero (p. ej. el JSON de Performance Analyzer) al lakehouse")
    u.add_argument("--workspace-id", required=True)
    u.add_argument("--lakehouse-id", required=True)
    u.add_argument("--file", required=True)
    u.add_argument("--dest", default="Files/PerfScenarios/Queries/")
    u.add_argument("--dry-run", action="store_true")
    u.set_defaults(func=cmd_upload)

    i = sub.add_parser("run-item", help="Lanza un notebook NB_* o un pipeline por nombre (repetir una fase)")
    i.add_argument("--workspace-id", required=True)
    i.add_argument("--name", required=True)
    i.add_argument("--params-file")
    i.add_argument("--param", action="append")
    i.add_argument("--wait", action="store_true")
    i.set_defaults(func=cmd_run_item)

    q = sub.add_parser("capacity-dax", help="Imprime las consultas DAX de Capacity Metrics para lanzarlas a mano")
    q.add_argument("--version", default="v53", choices=["v53", "v47", "v44", "v40"])
    q.add_argument("--capacity-id", default="00000000-0000-0000-0000-000000000000")
    q.add_argument("--date", default="2026-01-01")
    q.add_argument("--probes", action="store_true", help="Solo las sondas para detectar la versión de la app")
    q.set_defaults(func=cmd_capacity_dax)

    o = sub.add_parser("install-orchestrator", help="Instala el Fabric Load Test Orchestrator desde un clon local")
    o.add_argument("--repo", help="Clon de fabric-load-test-orchestrator (por defecto, el repo que contiene el gate)")
    o.add_argument("--workspace-id", required=True)
    o.add_argument("--lakehouse-id", required=True)
    o.add_argument("--overwrite", action="store_true")
    o.add_argument("--dry-run", action="store_true")
    o.set_defaults(func=cmd_install_orchestrator)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # consolas cp1252 de Windows
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())

