"""Functional tests of RunLoadTest_v3: parameters injected by the pipeline reach the DAG that is handed to runMultiple."""
import os
import sys
import time
import types

import pytest

from helpers import NOTEBOOKS, SAMPLE, find_cell, lakehouse_path, load_notebook, make_notebookutils, parameters_cell

NOTEBOOK = load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb")
PARAMETERS = parameters_cell(NOTEBOOK)
MAIN = find_cell(NOTEBOOK, "runMultiple")
# The cell also consolidates the CSV files with polars after the run; that part is not simulated here.
assert "# Consolodate CSV" in MAIN
MAIN = MAIN.split("    # Consolodate CSV")[0]


def run(tmp_path, injected=None):
    """Execute the Parameters cell, the injected cell and the main cell. Returns (namespace, captured DAG)."""
    captured = {}

    def run_multiple(dag):
        captured["dag"] = dag
        return {}

    sempy = types.ModuleType("sempy")
    sempy.fabric = types.ModuleType("sempy.fabric")
    sempy.fabric.get_lakehouse_id = lambda: "lakehouse-id"
    sempy.fabric.get_workspace_id = lambda: "workspace-id"
    namespace = {"os": os, "time": time, "sempy": sempy, "notebookutils": make_notebookutils(tmp_path, runmultiple=run_multiple)}
    exec(compile(lakehouse_path(PARAMETERS, tmp_path), "parameters", "exec"), namespace)
    exec(compile("\n".join(f"{k} = {v!r}" for k, v in (injected or {}).items()), "injected", "exec"), namespace)
    exec(compile(lakehouse_path(MAIN, tmp_path), "main", "exec"), namespace)
    return namespace, captured["dag"]


BASE = dict(queryfile=str(SAMPLE), dataset="Sales")


def test_the_value_sent_by_the_pipeline_replaces_the_default_and_reaches_the_dag(tmp_path):
    injected = dict(BASE, concurrent_threads=20, load_test_name="ramp-v3-SalesModel", workspace="", delay_sec=4, iterations=1,
                    enable_think_times=True, think_time_scale=1.0, max_think_time_sec=60.0, think_time_jitter_pct=0.1,
                    fallback_think_time_sec=0.0, ramp_up_sec=60.0, initial_user_jitter_sec=5.0, rls_users="")
    namespace, dag = run(tmp_path, injected)
    assert namespace["concurrent_threads"] == 20 != 6, "the Parameters cell default is 6"
    assert len(dag["activities"]) == 20 and dag["concurrency"] == 20
    assert all(a["path"] == "RunPerfScenario_v3" for a in dag["activities"])
    assert namespace["loadtestId"].startswith("ramp-v3-SalesModel-c20-")

    first = dag["activities"][0]["args"]
    assert first["workspace"] == "test-workspace", "an empty workspace means the current workspace"
    for key, value in (("enable_think_times", True), ("think_time_scale", 1.0), ("max_think_time_sec", 60.0),
                       ("think_time_jitter_pct", 0.1), ("initial_user_jitter_sec", 5.0), ("concurrent_threads", 20),
                       ("model", "Sales"), ("iterations", 1), ("delay_sec", 4), ("load_test_name", "ramp-v3-SalesModel"),
                       ("perf_analyzer_filename", str(SAMPLE))):
        assert first[key] == value, key
    assert {a["args"]["threadId"] for a in dag["activities"]} == set(range(20))


def test_ramp_up_spreads_the_start_of_the_virtual_users(tmp_path):
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=20, ramp_up_sec=60.0))
    delays = [a["args"]["start_delay_sec"] for a in dag["activities"]]
    assert delays[0] == 0 and delays == sorted(delays)
    assert delays[-1] == pytest.approx(60.0 * 19 / 20)


def test_without_pipeline_parameters_the_notebook_behaves_like_the_original(tmp_path):
    _, dag = run(tmp_path, dict(BASE))
    assert len(dag["activities"]) == 6
    assert all(a["args"]["enable_think_times"] is False and a["args"]["start_delay_sec"] == 0 for a in dag["activities"])


def test_text_parameters_are_normalised(tmp_path):
    _, dag = run(tmp_path, dict(BASE, concurrent_threads="60", enable_think_times="true", think_time_scale="0.5"))
    assert len(dag["activities"]) == 60
    assert dag["activities"][0]["args"]["enable_think_times"] is True
    assert dag["activities"][0]["args"]["think_time_scale"] == 0.5


def test_rls_users_are_spread_across_the_virtual_users(tmp_path):
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=5, rls_users=" a@contoso.com; b@contoso.com ,c@contoso.com "))
    assert [a["args"]["effective_username"] for a in dag["activities"]] == [
        "a@contoso.com", "b@contoso.com", "c@contoso.com", "a@contoso.com", "b@contoso.com"]


def test_without_rls_users_no_identity_is_impersonated(tmp_path):
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=3, rls_users=""))
    assert all(a["args"]["effective_username"] is None for a in dag["activities"])


@pytest.mark.parametrize("bad, error", [
    (dict(queryfile="/does/not/exist.json"), FileNotFoundError),
    (dict(dataset="  "), ValueError),
    (dict(concurrent_threads=301), ValueError),
    (dict(concurrent_threads=0), ValueError),
    (dict(think_time_jitter_pct=1.5), ValueError),
    (dict(think_time_scale=-1), ValueError),
])
def test_invalid_parameters_fail_before_anything_is_started(tmp_path, bad, error):
    with pytest.raises(error):
        run(tmp_path, {**BASE, **bad})
