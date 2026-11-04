"""Run summary of RunLoadTest_v3: summary.json, exit value and optional Delta tables, built from real scenario CSV files."""
import json
import os
import time
import types

import pytest

import make_sample_data as sample_data
from helpers import (NOTEBOOKS, SAMPLE, find_cell, lakehouse_path, load_notebook, make_notebookutils, parameters_cell,
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


class FakeSpark:
    def __init__(self):
        self.writes = []

    def createDataFrame(self, rows, schema):  # noqa: N802
        spark = self

        class Writer:
            def __init__(self):
                self.options = {}

            def mode(self, value):
                self.options["mode"] = value
                return self

            def option(self, key, value):
                self.options[key] = value
                return self

            def saveAsTable(self, name):  # noqa: N802
                spark.writes.append({"table": name, "rows": rows, "schema": schema, **self.options})

        return types.SimpleNamespace(write=Writer())


def run_final_cell(folder, write_tables):
    exits = []
    nbu = make_notebookutils(folder)
    nbu.notebook = types.SimpleNamespace(exit=exits.append)
    namespace = {"notebookutils": nbu, "spark": FakeSpark(), "print": lambda *a, **k: None,
                 "folder_path": str(folder), "loadtestId": folder.name, "load_test_name": "lt", "dataset": "Sales",
                 "concurrent_threads": 2, "write_results_to_tables": write_tables}
    exec(compile(HELPERS, "summary-helpers", "exec"), namespace)
    exec(compile(FINAL, "final", "exec"), namespace)
    return namespace, exits


def test_final_cell_writes_summary_and_exits_with_it(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c2-20260101-120000", 2)
    namespace, exits = run_final_cell(folder, write_tables=False)
    saved = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert json.loads(exits[0]) == saved and saved["status"] == "completed"
    assert namespace["spark"].writes == []


def test_final_cell_appends_typed_rows_to_the_delta_tables(fake_fabric, tmp_path):
    folder = scenario_run(tmp_path, "lt-c2-20260101-120000", 2)
    namespace, _ = run_final_cell(folder, write_tables=True)
    runs, queries = namespace["spark"].writes
    assert runs["table"] == "loadtest_runs" and queries["table"] == "loadtest_queries"
    assert runs["mode"] == queries["mode"] == "append"
    assert len(runs["rows"]) == 1 and len(queries["rows"]) == 2 * QUERIES
    names = [n for n, _ in namespace["QUERY_TABLE_SCHEMA"]]
    first = dict(zip(names, queries["rows"][0]))
    assert isinstance(first["duration"], float) and isinstance(first["thread_id"], int)
    assert first["status"] == "ok" and first["error"] is None
    old = helpers()["table_rows"]([{"duration": "1.5"}], namespace["QUERY_TABLE_SCHEMA"])[0]
    assert dict(zip(names, old))["status"] is None, "older CSV files without status give NULL, not an error"
    assert "`run_error` string" in runs["schema"]


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
