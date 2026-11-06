"""Consistency tests of the repository content and of the deployment package (no Fabric needed)."""
import ast
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

from helpers import NOTEBOOKS, ROOT, load_notebook, parameters_cell

sys.path.insert(0, str(ROOT / "tools"))
import build_package as bp  # noqa: E402

PIPELINES = ROOT / "pipelines"
UPSTREAM = ROOT / "upstream"

# Git blob SHA-1 of the upstream files at the pinned commit (see upstream/SOURCE.md): proves they are untouched.
UPSTREAM_BLOBS = {
    "RunLoadTest.ipynb": "1820b9a09ccc7ed9d7df727efa1e5914c3dd1747",
    "RunPerfScenario.ipynb": "bb63ac1daaa6cb7707730827c5245338c713ae0e",
    "readme.md": "f6f95f062215f2d636186f23dcfd5572b7df3e48",
}


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def assigned_names(source: str) -> set[str]:
    return {t.id for node in ast.parse(source).body if isinstance(node, ast.Assign) for t in node.targets if isinstance(t, ast.Name)}


def pipeline(name: str) -> dict:
    return json.loads((PIPELINES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,expected", UPSTREAM_BLOBS.items())
def test_upstream_files_are_byte_identical_to_the_pinned_commit(name, expected):
    assert git_blob_sha(UPSTREAM / name) == expected


def test_upstream_notebooks_carry_no_outputs():
    for name in ("RunLoadTest.ipynb", "RunPerfScenario.ipynb"):
        nb = json.loads((UPSTREAM / name).read_text(encoding="utf-8"))
        assert all(not c.get("outputs") for c in nb["cells"] if c["cell_type"] == "code")


@pytest.mark.parametrize("name,parameter_cells", [("RunPerfScenario_v3", 1), ("RunLoadTest_v3", 1), ("AnalyzeLoadTest_v3", 0)])
def test_notebooks_are_valid_clean_and_have_the_expected_parameters_cell(name, parameter_cells):
    nbformat = pytest.importorskip("nbformat")
    path = NOTEBOOKS / f"{name}.ipynb"
    nbformat.validate(nbformat.read(path, as_version=4))
    nb = load_notebook(path)
    tagged = [c for c in nb["cells"] if "parameters" in c.get("metadata", {}).get("tags", [])]
    # Fabric injects the pipeline parameters below the single cell tagged 'parameters'
    assert len(tagged) == parameter_cells
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            ast.parse("".join(cell["source"]).replace("%%", "#%%"))
            assert not cell.get("outputs") and cell.get("execution_count") is None
    assert "dependencies" not in nb["metadata"], "the installer adds the lakehouse binding"


def test_pipeline_notebook_parameters_exist_in_run_load_test():
    declared = assigned_names(parameters_cell(load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb")))
    activity = pipeline("PL_PerfTest_Ramp_v3")["properties"]["activities"][0]["typeProperties"]["activities"][0]
    sent = set(activity["typeProperties"]["parameters"])
    assert sent <= declared, f"the pipeline sends parameters the notebook does not declare: {sorted(sent - declared)}"


def test_run_load_test_forwards_every_scenario_parameter():
    scenario = assigned_names(parameters_cell(load_notebook(NOTEBOOKS / "RunPerfScenario_v3.ipynb")))
    load_test = "\n".join(
        "".join(c["source"]) for c in load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb")["cells"] if c["cell_type"] == "code")
    for name in scenario - {"perf_analyzer_filename", "loadtestId", "threadId", "effective_username", "model", "customdata"}:
        assert re.search(rf"\b{name}\b", load_test), f"RunLoadTest_v3 does not mention the scenario parameter {name}"


def test_child_pipeline_passes_every_parameter_the_parent_receives_and_nothing_unknown():
    child = pipeline("PL_PerfTest_Ramp_v3")["properties"]
    parent = pipeline("PL_PerfTest_MultiModel_v3")["properties"]
    execute = parent["activities"][0]["typeProperties"]["activities"][0]["typeProperties"]
    assert set(execute["parameters"]) <= set(child["parameters"])
    # every parent parameter except `models` is forwarded; `models` is consumed by the ForEach
    forwarded = set(re.findall(r"pipeline\(\)\.parameters\.(\w+)", json.dumps(execute["parameters"])))
    assert set(parent["parameters"]) - {"models"} <= forwarded
    # the child needs a value for each of its own parameters, either from the model item or from the parent
    assert set(child["parameters"]) == set(execute["parameters"])


def test_parent_runs_models_in_parallel_and_child_runs_levels_sequentially():
    parent = pipeline("PL_PerfTest_MultiModel_v3")["properties"]["activities"][0]
    child = pipeline("PL_PerfTest_Ramp_v3")["properties"]["activities"][0]
    assert parent["typeProperties"]["isSequential"] is False and 1 < parent["typeProperties"]["batchCount"] <= 50
    assert child["typeProperties"]["isSequential"] is True
    assert pipeline("PL_PerfTest_Ramp_v3")["properties"]["parameters"]["ramp_levels"]["type"] == "Array"


def test_rls_parameters_travel_from_the_parent_to_the_notebook_with_backward_compatible_defaults():
    parent = pipeline("PL_PerfTest_MultiModel_v3")["properties"]
    child = pipeline("PL_PerfTest_Ramp_v3")["properties"]
    notebook = child["activities"][0]["typeProperties"]["activities"][0]["typeProperties"]["parameters"]
    execute = parent["activities"][0]["typeProperties"]["activities"][0]["typeProperties"]["parameters"]
    defaults = {"rls_source": "list", "rls_scope": "global", "rls_users": "", "rls_users_file": ""}
    for name, value in defaults.items():
        assert parent["parameters"][name]["defaultValue"] == child["parameters"][name]["defaultValue"] == value
        assert execute[name]["value"] == f"@pipeline().parameters.{name}"
        assert notebook[name]["value"]["value"] == f"@pipeline().parameters.{name}"
    # the model item travels as JSON so that optional keys (users, users_file) never break the expression
    assert execute["model_settings"]["value"] == "@string(item())"
    assert "model_settings" not in parent["parameters"] and child["parameters"]["model_settings"]["defaultValue"] == ""
    assert notebook["model_settings"]["value"]["value"] == "@pipeline().parameters.model_settings"
    declared = assigned_names(parameters_cell(load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb")))
    assert {"rls_source", "rls_scope", "rls_users", "rls_users_file", "model_settings"} <= declared


def test_pipelines_have_a_safe_first_run_and_placeholders_only():
    child = pipeline("PL_PerfTest_Ramp_v3")["properties"]["parameters"]
    parent = pipeline("PL_PerfTest_MultiModel_v3")["properties"]["parameters"]
    assert child["ramp_levels"]["defaultValue"] == parent["ramp_levels"]["defaultValue"] == [1, 5, 10]
    assert parent["models"]["defaultValue"][0]["model_key"] == "CHANGE_ME_MODEL_KEY"
    for name, tokens in bp.TOKENS.items():
        text = (PIPELINES / f"{name}.json").read_text(encoding="utf-8")
        assert all(t in text for t in tokens)
        assert not bp.GUID.search(text)


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    target = bp.build(tmp_path_factory.mktemp("dist"))
    with zipfile.ZipFile(target) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_package_contains_the_manifest_the_items_and_the_installer(package):
    assert set(package) == {"manifest.json", bp.INSTALLER, *(rel for _, _, rel, _ in bp.ITEMS)}


def test_manifest_hashes_match_and_items_are_in_dependency_order(package):
    manifest = json.loads(package["manifest.json"])
    assert manifest["version"] == bp.VERSION and manifest["package"] == bp.PACKAGE
    for item in manifest["items"]:
        assert hashlib.sha256(package[item["file"]]).hexdigest() == item["sha256"]
    names = [i["name"] for i in manifest["items"]]
    assert names.index("RunLoadTest_v3") < names.index("PL_PerfTest_Ramp_v3") < names.index("PL_PerfTest_MultiModel_v3")
    assert manifest["folders"] == bp.FOLDERS


def test_package_has_no_environment_specific_content(package):
    assert bp.find_problems({k: v for k, v in package.items()}) == []


def good_notebook(**changes):
    nb = {"cells": [{"cell_type": "code", "source": ["print(1)"], "metadata": {}, "outputs": [], "execution_count": None}], "metadata": {}}
    nb.update(changes)
    return json.dumps(nb).encode()


@pytest.mark.parametrize("payload,expected", [
    (b'{"id": "0badf00d-0000-4000-8000-00000000000a"}', "GUID"),
    (b'{"owner": "someone@real-company.com"}', "e-mail"),
    (b'{"tenant": "contoso.onmicrosoft.com"}', "onmicrosoft.com"),
])
def test_leak_detection_in_text_files(payload, expected):
    problems = bp.find_problems({"pipelines/x.json": payload})
    assert len(problems) >= 1 and any(expected in p for p in problems)


def test_documentation_email_domains_are_allowed():
    assert bp.find_problems({"pipelines/x.json": b'{"rls": "user@contoso.com"}'}) == []


def test_leak_detection_in_notebooks():
    dirty = json.dumps({"cells": [{"cell_type": "code", "source": ["x = 1"], "metadata": {"cellStatus": {"a": 1}},
                                   "outputs": [{"output_type": "stream"}], "execution_count": 3}],
                        "metadata": {"dependencies": {"lakehouse": {}}}}).encode()
    text = " | ".join(bp.find_problems({"notebooks/n.ipynb": dirty}))
    assert "lakehouse binding" in text and "saved outputs" in text and "cellStatus" in text
    assert bp.find_problems({"notebooks/n.ipynb": good_notebook()}) == []


def test_notebook_cell_ids_are_not_treated_as_references():
    nb = json.loads(good_notebook())
    nb["cells"][0]["id"] = "0badf00d-0000-4000-8000-00000000000a"
    assert bp.find_problems({"notebooks/n.ipynb": json.dumps(nb).encode()}) == []


def test_deny_list_blocks_a_string_and_the_build_fails(tmp_path, monkeypatch):
    assert bp.find_problems({"pipelines/x.json": b'{"a": "My-Secret-Lakehouse"}'}, deny=["my-secret-lakehouse"])
    with pytest.raises(SystemExit):
        bp.build(tmp_path, deny=["PL_PerfTest_Ramp_v3"])
