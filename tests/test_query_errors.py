"""A failed query no longer ends a virtual user: it is a row with status 'error', and the CSV is written even on failure."""
import csv
import json
import sys

import pytest

import make_sample_data as sample_data
from helpers import (NOTEBOOKS, SAMPLE, SECRET_TOKEN, code_cells, find_cell, load_notebook, run_scenario_user)

QUERIES = sum(len(a[2]) for a in sample_data.ACTIONS)
BASE = dict(perf_analyzer_filename=str(SAMPLE), threadId=0, concurrent_threads=1, effective_username=None, model="Sales",
            workspace="ws", customdata=None, delay_sec=0, enable_think_times=False)


def read_rows(root, run_id, user=0):
    path = root / "Files" / "PerfScenarios" / "logs" / run_id / f"{run_id}_user_{user}.csv"
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def failing_every(monkeypatch, n, message):
    """Make every n-th query fail inside ExecuteReader, like a timeout or a throttling rejection would."""
    adomd = sys.modules["Microsoft.AnalysisServices.AdomdClient"]
    calls = {"n": 0, "reopened": 0}

    class Command:
        CommandText = ""

        def ExecuteReader(self):  # noqa: N802
            calls["n"] += 1
            if calls["n"] % n == 0:
                raise RuntimeError(message)
            return type("R", (), {"Read": lambda self: False, "Close": lambda self: None})()

    class Connection(adomd.AdomdConnection):
        State = "Open"

        def CreateCommand(self):  # noqa: N802
            return Command()

    monkeypatch.setattr(adomd, "AdomdConnection", Connection)
    return calls


def test_failed_queries_are_recorded_and_the_user_continues(fake_fabric, tmp_path, monkeypatch):
    failing_every(monkeypatch, 3, f"Timeout expired; Password={SECRET_TOKEN}\nline two")
    printed = run_scenario_user(tmp_path, loadtestId="run-err", iterations=2, **BASE)
    rows = read_rows(tmp_path, "run-err")
    assert len(rows) == 2 * QUERIES, "every query of every iteration has a row, failed or not"
    failed = [r for r in rows if r["status"] == "error"]
    assert len(failed) == (2 * QUERIES) // 3
    assert all(r["status"] == "ok" and r["error"] == "" for r in rows if r not in failed)
    assert all(r["rows"] == "0" and r["error"].startswith("RuntimeError: Timeout expired") for r in failed)
    assert all("\n" not in r["error"] for r in failed)
    log = (tmp_path / "Files" / "PerfScenarios" / "logs" / "run-err" / "error.log").read_text(encoding="utf-8")
    assert log.count("query error") == len(failed)
    assert SECRET_TOKEN not in log and SECRET_TOKEN not in json.dumps(rows) and "<redacted-token>" in log
    assert f"{len(failed)} of {2 * QUERIES} queries failed" in printed


def test_a_closed_connection_is_reopened_after_an_error(fake_fabric, tmp_path, monkeypatch):
    adomd = sys.modules["Microsoft.AnalysisServices.AdomdClient"]
    opened = []

    class Command:
        CommandText = ""

        def __init__(self, con):
            self.con = con

        def ExecuteReader(self):  # noqa: N802
            if self.con.State != "Open":
                raise RuntimeError("connection is closed")
            if len(opened) == 1:  # the first query breaks the connection
                self.con.State = "Closed"
                raise RuntimeError("session ended")
            return type("R", (), {"Read": lambda self: False, "Close": lambda self: None})()

    class Connection(adomd.AdomdConnection):
        State = "Closed"

        def Open(self):  # noqa: N802
            opened.append(1)
            self.State = "Open"

        def Close(self):  # noqa: N802
            self.State = "Closed"

        def CreateCommand(self):  # noqa: N802
            return Command(self)

    monkeypatch.setattr(adomd, "AdomdConnection", Connection)
    run_scenario_user(tmp_path, loadtestId="run-reopen", iterations=1, **BASE)
    rows = read_rows(tmp_path, "run-reopen")
    assert len(opened) == 2, "the connection is opened again after the error"
    assert [r["status"] for r in rows].count("error") == 1


def test_partial_results_are_written_when_the_user_stops(fake_fabric, tmp_path):
    # delay_sec = -1 makes the wait after the first query fail: the user stops, but the row it already has is kept
    with pytest.raises(ValueError):
        run_scenario_user(tmp_path, loadtestId="run-stop", iterations=3, **{**BASE, "delay_sec": -1})
    rows = read_rows(tmp_path, "run-stop")
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["query_number"] == "1"
    log = (tmp_path / "Files" / "PerfScenarios" / "logs" / "run-stop" / "error.log").read_text(encoding="utf-8")
    assert SECRET_TOKEN not in log


def test_the_run_summary_counts_the_failed_queries(fake_fabric, tmp_path, monkeypatch):
    failing_every(monkeypatch, 4, "throttled")
    for user in range(2):
        run_scenario_user(tmp_path, loadtestId="lt-c2-x", iterations=1, **{**BASE, "threadId": user, "concurrent_threads": 2})
    namespace = {}
    exec(compile(find_cell(load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb"), "def summarize_run_folder"), "h", "exec"), namespace)
    s = namespace["summarize_run_folder"](str(tmp_path / "Files" / "PerfScenarios" / "logs" / "lt-c2-x"), "lt-c2-x", "lt", "Sales", 2)
    assert s["status"] == "completed_with_errors"
    assert s["failed_queries"] == (2 * QUERIES) // 4 and s["missing_users"] == 0
    assert s["error_rate"] == pytest.approx(s["failed_queries"] / (2 * QUERIES), abs=1e-4)


def test_the_reader_is_closed_even_if_reading_fails():
    source = find_cell(load_notebook(NOTEBOOKS / "RunPerfScenario_v3.ipynb"), "def run_query")
    namespace = {"AdomdConnection": object}
    head = source.split("# load_queries()")[0]
    for line in ("tom = fabric.create_tom_server()", "import sempy.fabric as fabric",
                 "from Microsoft.AnalysisServices.AdomdClient import AdomdConnection"):
        head = head.replace(line, "")
    exec(compile(head, "run_query", "exec"), namespace)
    closed = []

    class Reader:
        def Read(self):  # noqa: N802
            raise RuntimeError("network")

        def Close(self):  # noqa: N802
            closed.append(True)

    command = type("C", (), {"CommandText": "", "ExecuteReader": lambda self: Reader()})()
    con = type("Con", (), {"CreateCommand": lambda self: command})()
    with pytest.raises(RuntimeError):
        namespace["run_query"](con, "EVALUATE {1}")
    assert closed == [True]


def test_scenario_notebook_still_has_four_code_cells():
    assert len(code_cells(load_notebook(NOTEBOOKS / "RunPerfScenario_v3.ipynb"))) == 4


def test_stop_on_query_error_restores_fail_fast_but_keeps_the_rows(fake_fabric, tmp_path, monkeypatch):
    failing_every(monkeypatch, 3, "Timeout expired")
    with pytest.raises(RuntimeError, match="stop_on_query_error"):
        run_scenario_user(tmp_path, loadtestId="run-stop", iterations=2, stop_on_query_error=True, **BASE)
    rows = read_rows(tmp_path, "run-stop")
    assert len(rows) == 3, "the user stops at its first failed query (the third), after recording it"
    assert [r["status"] for r in rows] == ["ok", "ok", "error"]


def test_stop_on_query_error_is_forwarded_by_both_pipelines_and_the_driver():
    from helpers import ROOT
    ramp = json.loads((ROOT / "pipelines" / "PL_PerfTest_Ramp_v3.json").read_text(encoding="utf-8"))
    multi = json.loads((ROOT / "pipelines" / "PL_PerfTest_MultiModel_v3.json").read_text(encoding="utf-8"))
    assert ramp["properties"]["parameters"]["stop_on_query_error"]["defaultValue"] is False
    assert multi["properties"]["parameters"]["stop_on_query_error"]["defaultValue"] is False
    driver = "".join("".join(c["source"]) for c in load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb")["cells"])
    assert '"stop_on_query_error" : stop_on_query_error' in driver


def test_fail_on_error_rate_is_forwarded_by_both_pipelines():
    from helpers import ROOT
    for name in ("PL_PerfTest_Ramp_v3.json", "PL_PerfTest_MultiModel_v3.json"):
        text = (ROOT / "pipelines" / name).read_text(encoding="utf-8")
        pipeline = json.loads(text)
        assert pipeline["properties"]["parameters"]["fail_on_error_rate"] == {"type": "Float", "defaultValue": 1.0}
        assert "pipeline().parameters.fail_on_error_rate" in text, f"{name} must forward fail_on_error_rate"
    driver = "".join("".join(c["source"]) for c in load_notebook(NOTEBOOKS / "RunLoadTest_v3.ipynb")["cells"])
    assert "fail_on_error_rate = 1.0" in driver
