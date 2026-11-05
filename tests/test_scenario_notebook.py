"""Functional tests of RunPerfScenario_v3: the notebook is executed with a fake ADOMD connection and writes real CSV files."""
import csv
import time
from pathlib import Path

import pytest

from helpers import SAMPLE, SECRET_TOKEN, run_scenario_user
import make_sample_data as sample_data

QUERIES_IN_SAMPLE = sum(len(a[2]) for a in sample_data.ACTIONS)  # 11
ACTIONS_IN_SAMPLE = len(sample_data.ACTIONS)  # 5

BASE = dict(perf_analyzer_filename=str(SAMPLE), threadId=3, concurrent_threads=5,
            effective_username="user@contoso.com", model="Sales", workspace="ws", customdata=None)


def run(root, loadtest_id, **params):
    """Run one virtual user; the BASE parameters play the role of what RunLoadTest passes to the scenario."""
    return run_scenario_user(root, **{**BASE, "loadtestId": loadtest_id, **params})


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def result_files(root: Path, loadtest_id: str):
    folder = root / "Files" / "PerfScenarios" / "logs" / loadtest_id
    return folder, folder / f"{loadtest_id}_user_3.csv", folder / "thinktimes" / f"{loadtest_id}_user_3_thinktimes.csv"


def all_text(root: Path) -> str:
    return "".join(p.read_text(errors="ignore") for p in root.rglob("*") if p.is_file())


def test_with_think_times_disabled_the_original_behaviour_is_kept(fake_fabric, tmp_path):
    printed = run(tmp_path, "run-a", iterations=1, delay_sec=0.01, enable_think_times=False)
    folder, results, think = result_files(tmp_path, "run-a")
    rows = read_csv(results)
    assert len(rows) == QUERIES_IN_SAMPLE
    assert [int(r["query_number"]) for r in rows] == list(range(1, QUERIES_IN_SAMPLE + 1))
    assert not think.exists(), "no think-time file is written when the feature is disabled"
    assert all(float(r["applied_think_time_sec"]) == 0 for r in rows)
    assert SECRET_TOKEN not in printed and "Initial Catalog=Sales" in printed


def test_think_times_are_applied_once_per_action_and_logged(fake_fabric, tmp_path):
    started = time.time()
    run(tmp_path, "run-b", iterations=1, delay_sec=2, enable_think_times=True,
                      think_time_scale=0.02, max_think_time_sec=60.0, think_time_jitter_pct=0.1,
                      start_delay_sec=0.2, initial_user_jitter_sec=0.1)
    elapsed = time.time() - started
    folder, results, think = result_files(tmp_path, "run-b")
    rows = read_csv(results)
    pauses = read_csv(think)
    actions = [r for r in pauses if r["source_label"] != "initial_offset"]
    offsets = [r for r in pauses if r["source_label"] == "initial_offset"]

    assert len(rows) == QUERIES_IN_SAMPLE
    assert len(actions) == ACTIONS_IN_SAMPLE, "one pause per action, not one per query"
    assert len(offsets) == 1 and 0.2 <= float(offsets[0]["applied_think_time_sec"]) <= 0.35
    for pause in actions:
        original, applied = float(pause["original_think_time_sec"]), float(pause["applied_think_time_sec"])
        assert float(pause["scaled_think_time_sec"]) == pytest.approx(original * 0.02, abs=0.002)
        assert original * 0.02 * 0.9 - 0.002 <= applied <= original * 0.02 * 1.1 + 0.002
        assert pause["sleep_start_utc"] <= pause["sleep_end_utc"]
        assert int(pause["queries_in_action"]) >= 1
    assert sum(1 for r in rows if float(r["applied_think_time_sec"]) > 0) <= ACTIONS_IN_SAMPLE - 1
    assert all("action_index" in r and "source_label" in r for r in rows)
    assert [int(r["action_index"]) for r in rows] == sorted(int(r["action_index"]) for r in rows), "queries are grouped by action"
    # delay_sec must apply between iterations (the upstream notebook also waits once after the last one: ~2 s here),
    # never once per query (that would take 11 x 2 s = 22 s)
    assert elapsed < 6, f"took {elapsed:.1f}s: delay_sec seems to be applied per query"


def test_scale_zero_removes_the_internal_pauses_but_keeps_delay_between_iterations(fake_fabric, tmp_path):
    started = time.time()
    run(tmp_path, "run-c", iterations=2, delay_sec=0.4, enable_think_times=True, think_time_scale=0.0)
    elapsed = time.time() - started
    _, results, think = result_files(tmp_path, "run-c")
    pauses = read_csv(think)
    assert len(pauses) == 2 * ACTIONS_IN_SAMPLE
    assert all(float(p["applied_think_time_sec"]) == 0 for p in pauses)
    assert len(read_csv(results)) == 2 * QUERIES_IN_SAMPLE
    assert elapsed >= 0.7, "delay_sec must still apply between the iterations"


@pytest.mark.parametrize("bad, message", [
    ({"think_time_scale": -1}, "think_time_scale"),
    ({"think_time_jitter_pct": 2}, "think_time_jitter_pct"),
    ({"max_think_time_sec": -5}, "max_think_time_sec"),
])
def test_invalid_think_time_parameters_are_rejected(fake_fabric, tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        run(tmp_path, "run-d", iterations=1, delay_sec=0, enable_think_times=True, **bad)


def test_the_access_token_is_never_written_anywhere(fake_fabric, tmp_path):
    printed = run(tmp_path, "run-e", iterations=1, delay_sec=0, enable_think_times=True, think_time_scale=0.01)
    assert SECRET_TOKEN not in printed
    assert SECRET_TOKEN not in all_text(tmp_path)


def test_a_failure_is_logged_without_the_token_and_re_raised(fake_fabric, tmp_path, monkeypatch):
    import sys
    adomd = sys.modules["Microsoft.AnalysisServices.AdomdClient"]

    class Failing(adomd.AdomdConnection):
        def Open(self):  # noqa: N802
            raise RuntimeError("boom")

    monkeypatch.setattr(adomd, "AdomdConnection", Failing)
    with pytest.raises(RuntimeError, match="boom"):
        run(tmp_path, "run-f", iterations=1, delay_sec=0)
    error_log = (tmp_path / "Files" / "PerfScenarios" / "logs" / "run-f" / "error.log").read_text()
    assert "boom" in error_log and SECRET_TOKEN not in error_log


def _capture_connections(monkeypatch):
    import sys
    adomd = sys.modules["Microsoft.AnalysisServices.AdomdClient"]
    opened = []

    class Recording(adomd.AdomdConnection):
        AccessToken = None
        OnAccessTokenExpired = None

        def Open(self):  # noqa: N802
            opened.append(self)

    monkeypatch.setattr(adomd, "AdomdConnection", Recording)
    return opened


def test_without_sempy_the_token_goes_in_the_connection_string(fake_fabric, tmp_path, monkeypatch):
    opened = _capture_connections(monkeypatch)
    run(tmp_path, "run-g", iterations=1, delay_sec=0)
    assert opened and opened[0].connection_string.endswith(f"password={SECRET_TOKEN};")


def test_with_sempy_the_connection_uses_its_access_token_and_refresh(fake_fabric, tmp_path, monkeypatch):
    import sys
    import types
    opened = _capture_connections(monkeypatch)
    calls = []

    def refresh_tom_access_token(current, credential=None):
        calls.append(credential)
        return "SEMPY-TOKEN"

    utils = types.ModuleType("sempy.fabric._client._utils")
    utils.refresh_tom_access_token = refresh_tom_access_token
    client = types.ModuleType("sempy.fabric._client")
    system = types.ModuleType("System")
    system.Func = type("Func", (), {"__class_getitem__": classmethod(lambda cls, _: (lambda f: f))})
    analysis = sys.modules["Microsoft.AnalysisServices"]
    monkeypatch.setattr(analysis, "AccessToken", object, raising=False)
    for name, module in {"sempy.fabric._client": client, "sempy.fabric._client._utils": utils, "System": system}.items():
        monkeypatch.setitem(sys.modules, name, module)
    run(tmp_path, "run-h", iterations=1, delay_sec=0)
    con = opened[0]
    assert "password=" not in con.connection_string.lower()
    assert con.AccessToken == "SEMPY-TOKEN" and calls == [None]
    assert con.OnAccessTokenExpired("old") == "SEMPY-TOKEN"
