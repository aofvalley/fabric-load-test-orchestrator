"""Coherencia de los artefactos: notebooks, pipeline, plugin, CI y ausencia de secretos."""

import json
import re
from pathlib import Path

import yaml

from promotion_gate.notebooks import load_notebooks, parameters_of

ROOT = Path(__file__).resolve().parents[1]
PIPE = json.loads((ROOT / "pipelines" / "PL_PromotionGate.json").read_text(encoding="utf-8"))

# Parámetros de PL_PerfTest_MultiModel_v3 (fabric-load-test-orchestrator 3.4.0, docs/pipeline-parameters.md). Dentro del repo del
# orquestador (promotion-gate/) se leen del pipeline real, para que un renombrado no pase sin avisar: Fabric ignora los desconocidos.
_REAL = ROOT.parent / "pipelines" / "PL_PerfTest_MultiModel_v3.json"
ORCHESTRATOR_PARAMS = set(json.loads(_REAL.read_text(encoding="utf-8"))["properties"]["parameters"]) if _REAL.exists() else {
    "models", "test_name_prefix", "ramp_levels", "iterations", "delay_sec", "enable_think_times", "think_time_scale",
    "max_think_time_sec", "think_time_jitter_pct", "fallback_think_time_sec", "ramp_up_sec", "initial_user_jitter_sec",
    "rls_source", "rls_scope", "rls_users", "rls_users_file", "stop_on_query_error", "write_results_to_tables",
}


def _walk(activities):
    for a in activities:
        yield a
        tp = a.get("typeProperties", {})
        for key in ("ifTrueActivities", "ifFalseActivities", "activities"):
            yield from _walk(tp.get(key, []))


ACTS = {a["name"]: a for a in _walk(PIPE["properties"]["activities"])}


def test_notebooks_load_the_wheel_before_parameters_without_pip():
    nbs = load_notebooks(ROOT / "notebooks")
    assert set(nbs) == {"NB_Gate_ModelReview", "NB_Gate_LoadTestReport", "NB_Gate_CapacityMetrics", "NB_Gate_Verdict"}
    for name, nb in nbs.items():
        code = [c for c in nb["cells"] if c["cell_type"] == "code"]
        assert 'sys.path.insert(0, "{{GATE_WHEEL}}")' in "".join(code[0]["source"]), name
        assert not any(line.lstrip().startswith("%pip") for c in code for line in c["source"]), name  # %pip falla en sesiones de alta concurrencia
        assert "parameters" in code[1]["metadata"].get("tags", []), name
        assert "run_id" in parameters_of(nb) and "gate_config" in parameters_of(nb)
        assert "notebookutils.notebook.exit(json.dumps(" in "".join(code[-1]["source"]), name


def test_pipeline_notebook_parameters_exist_in_notebooks():
    nbs = load_notebooks(ROOT / "notebooks")
    for name, nb in nbs.items():
        act = ACTS[name]
        assert act["typeProperties"]["notebookId"] == "{{NOTEBOOK:%s}}" % name
        sent = set(act["typeProperties"]["parameters"]) - {"_inlineInstallationEnabled"}
        assert sent <= set(parameters_of(nb)), (name, sent - set(parameters_of(nb)))
        assert act["typeProperties"]["parameters"]["_inlineInstallationEnabled"] == {"value": True, "type": "bool"}


def test_pipeline_forwards_only_known_orchestrator_parameters():
    run = ACTS["Run_LoadTest"]["typeProperties"]
    assert run["pipeline"]["referenceName"] == "{{PIPELINE:PL_PerfTest_MultiModel_v3}}"
    assert set(run["parameters"]) <= ORCHESTRATOR_PARAMS
    declared = set(PIPE["properties"]["parameters"])
    used = set(re.findall(r"pipeline\(\)\.parameters\.(\w+)", json.dumps(PIPE)))
    assert used <= declared, used - declared


def test_pipeline_placeholders_and_fail_gate():
    text = json.dumps(PIPE)
    placeholders = set(re.findall(r"\{\{([^}]+)\}\}", text))
    assert placeholders == {"WORKSPACE_ID", "PIPELINE:PL_PerfTest_MultiModel_v3", "NOTEBOOK:NB_Gate_ModelReview",
                            "NOTEBOOK:NB_Gate_LoadTestReport", "NOTEBOOK:NB_Gate_CapacityMetrics", "NOTEBOOK:NB_Gate_Verdict"}
    assert ACTS["Fail_Gate"]["type"] == "Fail"
    assert ACTS["NB_Gate_Verdict"]["dependsOn"][0]["dependencyConditions"] == ["Completed"]


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    return yaml.safe_load(text.split("---\n")[1])


def test_plugin_manifests_and_skills():
    plugin = ROOT / "plugin"
    copilot = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert copilot["name"] == claude["name"] == "semantic-model-promotion-gate"
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert market["plugins"][0]["source"] == "./plugin"
    skills = sorted(p for p in (plugin / "skills").iterdir() if p.is_dir())
    assert {s.name for s in skills} == {"promotion-gate", "model-bpa-review", "load-test-run", "load-test-report",
                                        "capacity-metrics-review"}
    for s in skills:
        fm = _frontmatter(s / "SKILL.md")
        assert fm["name"] == s.name and len(fm["description"]) > 80
    for agent in [plugin / "agents" / "promotion-gate.md", plugin / "copilot" / "agents" / "promotion-gate.agent.md"]:
        assert _frontmatter(agent)["description"]


def test_ci_workflows_parse():
    gh = yaml.safe_load((ROOT / "ci" / "github" / "promotion-gate.yml").read_text(encoding="utf-8"))
    assert "workflow_dispatch" in gh[True] and "gate" in gh["jobs"] and "promote" in gh["jobs"]
    ado = yaml.safe_load((ROOT / "ci" / "azure-devops" / "promotion-gate.yml").read_text(encoding="utf-8"))
    assert [s["stage"] for s in ado["stages"]] == ["Gate", "Promote"]


GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
ALLOWED_GUIDS = {"11111111-2222-3333-4444-555555555555", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                 "0f0f0f0f-1111-2222-3333-444444444444", "00000000-0000-0000-0000-000000000000"}
# Ids ficticios de la demo de la app: repetitivos o con el bloque 0000-4000-8000.
PLACEHOLDER = re.compile(r"^(?:(.)\1{7}-|.*-0000-4000-8000-)", re.I)


def _versioned_files():
    import subprocess

    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "."],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line and (ROOT / line).is_file()]


def test_no_real_ids_or_upns_in_versioned_files():
    files = _versioned_files()
    assert any(f.name == "README.md" for f in files)
    for p in files:
        if p.suffix in {".whl", ".pyc", ".woff2", ".png"}:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        found = {g for g in GUID.findall(text) if g.lower() not in ALLOWED_GUIDS and not PLACEHOLDER.match(g)}
        assert not found, (p, found)
        assert "onmicrosoft" + ".com" not in text and "@microsoft" + ".com" not in text, p


def test_rls_follows_the_orchestrator_switches():
    """3.3.0: rls_source (list|file|none) y rls_scope; el gate prueba un modelo, así que basta el ámbito global."""
    run = ACTS["Run_LoadTest"]["typeProperties"]["parameters"]
    assert run["rls_scope"]["value"] == "global"
    source = run["rls_source"]["value"]
    assert "rls_users_file" in source and "'file'" in source and "'list'" in source and "'none'" in source
    assert run["rls_users_file"]["value"] == "@pipeline().parameters.rls_users_file"
    assert PIPE["properties"]["parameters"]["rls_users_file"] == {"type": "String", "defaultValue": ""}
