"""Run summary of RunLoadTest_v3: summary.json, exit value and optional Delta tables, built from real scenario CSV files."""
import json
import os
import time
import types

import pandas as pd
import pytest

import make_sample_data as sample_data
from helpers import (NOTEBOOKS, SAMPLE, SECRET_TOKEN, find_cell, lakehouse_path, load_notebook, make_notebookutils, parameters_cell,
                     run_scenario_user)

NOTEBOOK = load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb")
HELPERS = find_cell(NOTEBOOK, "def summarize_run_folder")
FINAL = find_cell(NOTEBOOK, "notebookutils.notebook.exit")
MAIN = find_cell(NOTEBOOK, "runMultiple").split("    # Consolodate CSV")[0]
QUERIES = sum(len(a[2]) for a in sample_data.ACTIONS)


def helpers():
    namespace = {}
    exec(compile(HELPERS, "summary-helpers", "exec"), namespace)
    return namespace


def scenario_run(root, run_id, users, model="Sales"):
    for thread in range(users):
        run_scenario_user(root, perf_analyzer_filename=str(SAMPLE), loadtestId=run_id, load_test_name="lt", threadId=thread,
                          concurrent_threads=users, effective_username=None, model=model, workspace="ws", customdata=None,
                          iterations=1, delay_sec=0, enable_think_times=False)
    return root / "Files" / "PerfScenarios" / "logs" / run_id


def test_percentile_is_linear_like_numpy():
    pct = helpers()["_percentile"]
    assert pct([1, 2, 3, 4], 50) == 2.5
    assert pct(list(range(1, 11)), 95) == pytest.approx(9.55)
    assert pct([], 50) is None


def test_summary_of_a_complete_run(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c3-20260101-120000", 3)
    s = helpers()["summarize_run_folder"](str(folder), "lt-c3-20260101-120000", "lt", "Sales", 3)
    assert s["status"] == "completed"
    assert s["users_with_results"] == 3 and s["missing_users"] == 0
    assert s["queries"] == s["expected_queries"] == 3 * QUERIES and s["queries_per_user"] == QUERIES
    assert s["failed_queries"] == 0 and s["error_rate"] == 0
    assert 0 < s["p50_s"] <= s["p95_s"] <= s["max_s"]
    assert s["start_utc"].endswith("Z") and s["start_utc"] <= s["end_utc"]
    json.dumps(s)


def test_lost_virtual_users_count_as_failed_queries(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c5-20260101-120000", 3)
    (folder / "error.log").write_text("user 3 : boom\nuser 4 : boom\n", encoding="utf-8")
    s = helpers()["summarize_run_folder"](str(folder), "lt-c5-20260101-120000", "lt", "Sales", 5)
    assert s["status"] == "completed_with_errors"
    assert s["missing_users"] == 2 and s["expected_queries"] == 5 * QUERIES
    assert s["error_rate"] == pytest.approx(0.4) and s["error_log_lines"] == 2


def test_rows_with_status_error_are_failed_and_excluded_from_percentiles(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    header = "thread_id,duration,start_time,status,error\n"
    (folder / "run_user_0.csv").write_text(header + "0,1.0,100,ok,\n0,9.0,102,error,timeout\n", encoding="utf-8")
    s = helpers()["summarize_run_folder"](str(folder), "run", "lt", "Sales", 1)
    assert s["failed_queries"] == 1 and s["error_rate"] == 0.5
    assert s["p95_s"] == s["max_s"] == 1.0


def test_a_run_without_results_is_failed(tmp_path):
    s = helpers()["summarize_run_folder"](str(tmp_path / "missing"), "x", "lt", "Sales", 4)
    assert s["status"] == "failed" and s["queries"] == 0 and s["error_rate"] == 1.0


class RecordingDelta:
    """Stands in for deltalake.write_deltalake and records every call."""

    def __init__(self, reject=()):
        self.calls = []
        self.reject = set(reject)

    def __call__(self, uri, data, **kwargs):
        if self.reject & set(kwargs):
            raise TypeError(f"unexpected keyword argument {sorted(self.reject & set(kwargs))[0]!r}")
        self.calls.append({"uri": uri, "data": data, **kwargs})


def run_final_cell(folder, write_tables, fail_on_error_rate=1.0, delta=None):
    exits = []
    nbu = make_notebookutils(folder)
    nbu.notebook = types.SimpleNamespace(exit=exits.append)
    nbu.runtime.context.update(currentWorkspaceId="ws-guid", defaultLakehouseId="lh-guid")
    namespace = {"notebookutils": nbu, "write_deltalake": delta or RecordingDelta(), "os": os,
                 "print": lambda *a, **k: None, "folder_path": str(folder), "loadtestId": folder.name,
                 "load_test_name": "lt", "dataset": "Sales", "concurrent_threads": 2,
                 "write_results_to_tables": write_tables, "fail_on_error_rate": fail_on_error_rate}
    exec(compile(HELPERS, "summary-helpers", "exec"), namespace)
    exec(compile(FINAL, "final", "exec"), namespace)
    return namespace, exits


def test_final_cell_writes_summary_and_exits_with_it(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c2-20260101-120000", 2)
    namespace, exits = run_final_cell(folder, write_tables=False)
    saved = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert json.loads(exits[0]) == saved and saved["status"] == "completed"
    assert namespace["write_deltalake"].calls == []


def test_driver_notebook_never_uses_spark():
    """RunLoadTest_v3 is a Python notebook (jupyter_python): there is no Spark session in Fabric."""
    import re
    for cell in NOTEBOOK["cells"]:
        if cell["cell_type"] != "code":
            continue
        code = "\n".join(line.split("#", 1)[0] for line in "".join(cell["source"]).splitlines())
        assert not re.search(r"\bspark\b", code), "use deltalake (write_deltalake), not spark"


def test_final_cell_appends_typed_rows_with_deltalake(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c2-20260101-120000", 2)
    namespace, exits = run_final_cell(folder, write_tables=True)
    runs, queries = namespace["write_deltalake"].calls
    root = "abfss://ws-guid@onelake.dfs.fabric.microsoft.com/lh-guid/Tables"
    assert runs["uri"] == f"{root}/loadtest_runs" and queries["uri"] == f"{root}/loadtest_queries"
    assert runs["mode"] == queries["mode"] == "append" and runs["schema_mode"] == "merge"
    assert runs["storage_options"] == {"bearer_token": SECRET_TOKEN, "use_fabric_endpoint": "true"}
    assert len(runs["data"]) == 1 and len(queries["data"]) == 2 * QUERIES
    assert str(runs["data"]["run_error"].dtype) == "string", "an all-null column needs a type for Arrow"
    assert str(queries["data"]["thread_id"].dtype) == "Int64" and str(queries["data"]["duration"].dtype) == "float64"
    first = queries["data"].iloc[0]
    assert first["status"] == "ok" and first["error"] is pd.NA
    assert json.loads(exits[0])["status"] == "completed"


def test_older_deltalake_without_schema_mode_falls_back_to_a_plain_append(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c2-20260101-120000", 2)
    namespace, _ = run_final_cell(folder, write_tables=True, delta=RecordingDelta(reject={"schema_mode"}))
    assert [set(c) - {"uri", "data"} for c in namespace["write_deltalake"].calls] == [{"mode", "storage_options"}] * 2


def test_fail_on_error_rate_fails_the_notebook_after_writing_the_summary(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c2-20260101-120000", 2)
    rows = (folder / "lt-c2-20260101-120000_user_0.csv").read_text(encoding="utf-8").splitlines()
    rows[1] = rows[1].replace(",ok,", ",error,")
    (folder / "lt-c2-20260101-120000_user_0.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="fail_on_error_rate"):
        run_final_cell(folder, write_tables=False, fail_on_error_rate=0.0)
    assert json.loads((folder / "summary.json").read_text(encoding="utf-8"))["failed_queries"] == 1
    _, exits = run_final_cell(folder, write_tables=False)
    assert json.loads(exits[0])["failed_queries"] == 1, "by default a run with failed queries still ends normally"


def test_a_failed_runmultiple_still_leaves_summary_json(tmp_path):
    def run_multiple(dag):
        raise RuntimeError("2 of 3 notebooks failed")

    sempy = types.ModuleType("sempy")
    sempy.fabric = types.ModuleType("sempy.fabric")
    sempy.fabric.get_lakehouse_id = lambda: "lakehouse-id"
    sempy.fabric.get_workspace_id = lambda: "workspace-id"
    namespace = {"os": os, "time": time, "sempy": sempy, "print": lambda *a, **k: None,
                 "notebookutils": make_notebookutils(tmp_path, runmultiple=run_multiple)}
    exec(compile(HELPERS, "summary-helpers", "exec"), namespace)
    exec(compile(lakehouse_path(parameters_cell(NOTEBOOK), tmp_path), "parameters", "exec"), namespace)
    exec(compile(f"queryfile = {str(SAMPLE)!r}\ndataset = 'Sales'\nconcurrent_threads = 3", "injected", "exec"), namespace)
    with pytest.raises(RuntimeError, match="failed"):
        exec(compile(lakehouse_path(MAIN, tmp_path), "main", "exec"), namespace)
    summary = json.loads((tmp_path / "Files" / "PerfScenarios" / "logs" / namespace["loadtestId"] / "summary.json")
                         .read_text(encoding="utf-8"))
    assert summary["status"] == "failed" and "2 of 3 notebooks failed" in summary["run_error"]
    assert summary["concurrent_threads"] == 3
