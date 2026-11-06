"""Functional tests of RunLoadTest_v3: parameters injected by the pipeline reach the DAG that is handed to runMultiple."""
import json
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


def identities(dag):
    return [a["args"]["effective_username"] for a in dag["activities"]]


def users_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def model_settings(**fields):
    return json.dumps({"model_key": "SalesA", "dataset": "Sales", "workspace": "", "queryfile": str(SAMPLE), **fields})


def test_defaults_keep_the_previous_behaviour_of_rls_users(tmp_path):
    namespace, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_users="a@contoso.com"))
    assert (namespace["rls_source"], namespace["rls_scope"]) == ("list", "global")
    assert identities(dag) == ["a@contoso.com", "a@contoso.com"]


def test_file_source_reads_one_upn_per_line_and_spreads_them(tmp_path):
    path = users_file(tmp_path, "users.txt", "\ufeff# test users\nA@contoso.com\n\n  b@contoso.com  # second\nc@contoso.com;d@contoso.com\n")
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=6, rls_source="file", rls_users_file=path))
    assert identities(dag) == ["A@contoso.com", "b@contoso.com", "c@contoso.com", "d@contoso.com", "A@contoso.com", "b@contoso.com"]


def test_file_source_removes_duplicates_ignoring_case_and_keeps_the_first_spelling(tmp_path):
    path = users_file(tmp_path, "users.txt", "Ann@contoso.com\nann@CONTOSO.com\nbob@contoso.com\n")
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=3, rls_source="file", rls_users_file=path))
    assert identities(dag) == ["Ann@contoso.com", "bob@contoso.com", "Ann@contoso.com"]


def test_file_source_ignores_rls_users(tmp_path):
    path = users_file(tmp_path, "users.txt", "file@contoso.com\n")
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_source="file", rls_users_file=path, rls_users="list@contoso.com"))
    assert set(identities(dag)) == {"file@contoso.com"}


def test_list_source_ignores_the_file(tmp_path):
    path = users_file(tmp_path, "users.txt", "file@contoso.com\n")
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_source="list", rls_users_file=path, rls_users="list@contoso.com"))
    assert set(identities(dag)) == {"list@contoso.com"}


def test_none_source_disables_impersonation_even_if_users_are_given(tmp_path):
    path = users_file(tmp_path, "users.txt", "file@contoso.com\n")
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_source="none", rls_users_file=path, rls_users="list@contoso.com"))
    assert identities(dag) == [None, None]


def test_global_scope_ignores_the_users_of_the_model(tmp_path):
    settings = model_settings(users=["own@contoso.com"])
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_scope="global", rls_users="all@contoso.com", model_settings=settings))
    assert set(identities(dag)) == {"all@contoso.com"}


def test_per_model_list_uses_the_users_of_the_model(tmp_path):
    settings = model_settings(users=["a@contoso.com", "b@contoso.com"])
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=3, rls_scope="per_model", rls_users="all@contoso.com", model_settings=settings))
    assert identities(dag) == ["a@contoso.com", "b@contoso.com", "a@contoso.com"]


def test_per_model_list_accepts_a_text_value_too(tmp_path):
    settings = model_settings(users="a@contoso.com, b@contoso.com")
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_scope="per_model", model_settings=settings))
    assert identities(dag) == ["a@contoso.com", "b@contoso.com"]


def test_per_model_file_uses_the_file_of_the_model(tmp_path):
    own = users_file(tmp_path, "sales_a.txt", "own1@contoso.com\nown2@contoso.com\n")
    other = users_file(tmp_path, "global.txt", "global@contoso.com\n")
    settings = model_settings(users_file=own)
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_source="file", rls_scope="per_model", rls_users_file=other,
                                model_settings=settings))
    assert identities(dag) == ["own1@contoso.com", "own2@contoso.com"]


def test_per_model_falls_back_to_the_global_value_when_the_model_has_none(tmp_path, capsys):
    other = users_file(tmp_path, "global.txt", "global@contoso.com\n")
    run(tmp_path, dict(BASE, concurrent_threads=2, rls_source="file", rls_scope="per_model", rls_users_file=other, model_settings=model_settings()))
    assert "global file (rls_users_file)" in capsys.readouterr().out
    _, dag = run(tmp_path, dict(BASE, concurrent_threads=2, rls_scope="per_model", rls_users="all@contoso.com", model_settings=model_settings()))
    assert set(identities(dag)) == {"all@contoso.com"}


def test_two_models_get_their_own_identities_from_the_same_notebook(tmp_path):
    first = users_file(tmp_path, "first.txt", "first@contoso.com\n")
    second = users_file(tmp_path, "second.txt", "second@contoso.com\n")
    common = dict(BASE, concurrent_threads=2, rls_source="file", rls_scope="per_model")
    _, dag_a = run(tmp_path, dict(common, model_settings=model_settings(users_file=first)))
    _, dag_b = run(tmp_path, dict(common, model_settings=model_settings(users_file=second)))
    assert set(identities(dag_a)) == {"first@contoso.com"} and set(identities(dag_b)) == {"second@contoso.com"}


def test_the_log_shows_where_the_identities_come_from_without_printing_them(tmp_path, capsys):
    path = users_file(tmp_path, "users.txt", "secret.user@contoso.com\nsecond.user@contoso.com\n")
    run(tmp_path, dict(BASE, concurrent_threads=5, rls_source="file", rls_users_file=path))
    out = capsys.readouterr().out
    assert "RLS identities: 2" in out and "global file (rls_users_file)" in out and "reused in turn" in out
    assert "secret.user" not in out


@pytest.mark.parametrize("injected, error, message", [
    (dict(rls_source="file", rls_users_file=""), ValueError, "no file was given"),
    (dict(rls_source="file", rls_users_file="/does/not/exist.txt"), FileNotFoundError, "Users file not found"),
    (dict(rls_source="database"), ValueError, "rls_source must be"),
    (dict(rls_scope="local"), ValueError, "rls_scope must be"),
    (dict(model_settings="{not json"), ValueError, "not valid JSON"),
    (dict(model_settings="[1, 2]"), ValueError, "must be a JSON object"),
    (dict(rls_users="not-an-upn"), ValueError, "not-an-upn"),
])
def test_invalid_rls_settings_fail_before_anything_is_started(tmp_path, injected, error, message):
    with pytest.raises(error, match=message):
        run(tmp_path, {**BASE, "concurrent_threads": 2, **injected})


def test_an_empty_users_file_is_an_error(tmp_path):
    path = users_file(tmp_path, "users.txt", "# nobody yet\n\n")
    with pytest.raises(ValueError, match="contains no users"):
        run(tmp_path, dict(BASE, rls_source="file", rls_users_file=path))


def test_invalid_lines_are_reported_with_their_line_number(tmp_path):
    path = users_file(tmp_path, "users.txt", "ok@contoso.com\nnot a upn\n")
    with pytest.raises(ValueError, match=r"line 2.*'not a upn'|line 2.*not"):
        run(tmp_path, dict(BASE, rls_source="file", rls_users_file=path))


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
