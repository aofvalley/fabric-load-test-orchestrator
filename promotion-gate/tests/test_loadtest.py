from conftest import write_run

from promotion_gate.checks import FAIL, PASS, WARN, percentile
from promotion_gate.config import load_config
from promotion_gate.loadtest import evaluate_load_test, read_runs, summarize, sustained_level


def _cfg(**load):
    return load_config({"load_test": {"target_level": 10, **load}})


def test_percentile_matches_numpy_linear():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 9.55
    assert percentile([7], 95) == 7


def test_reads_only_the_requested_prefix(logs):
    runs = read_runs(logs, "gate-r1")
    assert [r["level"] for r in runs] == [1, 5, 10]
    assert {r["model_key"] for r in runs} == {"ventas"}


def test_summary_levels_and_window(logs):
    s = summarize(read_runs(logs, "gate-r1"))
    m = s["models"][0]
    assert m["model"] == "Ventas" and m["queries_per_user"] == 3
    lv10 = m["levels"][-1]
    assert lv10["users_seen"] == 10 and lv10["queries"] == 30 and lv10["failed_queries"] == 0
    assert lv10["p95"] > m["levels"][0]["p95"]
    assert s["window"]["start_utc"].endswith("Z") and s["window"]["start_utc"] < s["window"]["end_utc"]


def test_failed_users_count_as_missing_queries_and_errors_are_redacted(tmp_path):
    root = tmp_path / "logs"
    write_run(root, "p", "m", 2, 1_000.0, ts="20261104-100000")
    write_run(root, "p", "m", 4, 2_000.0, failed_users=1, ts="20261104-100100")
    lv = summarize(read_runs(root, "p"))["models"][0]["levels"][1]
    assert lv["expected_queries"] == 12 and lv["failed_queries"] == 3 and lv["error_rate"] == 0.25
    assert lv["error_log_lines"] == 1
    assert "ana@contoso.com" not in lv["error_samples"][0] and "<upn>" in lv["error_samples"][0]


def test_slow_visuals_distinguish_contention_from_slow_query(logs):
    m = summarize(read_runs(logs, "gate-r1"), slow_query_sec=1.0)["models"][0]
    by = {v["visual"]: v for v in m["slow_visuals"]}
    assert by["Matriz detalle"]["growth"] >= 2 and by["Matriz detalle"]["slow"]
    assert by["Ventas por mes"]["growth"] < 1.2 and not by["Ventas por mes"]["slow"]
    assert m["slow_queries"][0]["visual"] == "Matriz detalle" and "\n" not in m["slow_queries"][0]["dax"]


def test_evaluate_pass_and_fail(logs):
    s = summarize(read_runs(logs, "gate-r1"))
    ok = {c.id: c.status for c in evaluate_load_test(s, _cfg(p95_sec=10, p50_sec=10, max_p95_growth_ratio=5))}
    assert ok["load_test.ventas.p95"] == PASS and ok["load_test.ventas.errors"] == PASS
    assert ok["load_test.ventas.ramp"] == PASS and ok["load_test.ventas.sustained"] == PASS
    bad = {c.id: c.status for c in evaluate_load_test(s, _cfg(p95_sec=1.0, max_p95_growth_ratio=1.2))}
    assert bad["load_test.ventas.p95"] == FAIL and bad["load_test.ventas.scalability"] == WARN


def test_target_not_reached_is_warned(logs):
    s = summarize(read_runs(logs, "gate-r1"))
    checks = {c.id: c for c in evaluate_load_test(s, load_config({"load_test": {"target_level": 60, "p95_sec": 10}}))}
    assert checks["load_test.ventas.ramp"].status == WARN
    assert checks["load_test.ventas.p95"].evidence["level"] == 10


def test_sustained_level_stops_at_first_breach(logs):
    levels = summarize(read_runs(logs, "gate-r1"))["models"][0]["levels"]
    p95s = [lv["p95"] for lv in levels]
    assert sustained_level(levels, {"p95_sec": (p95s[0] + p95s[1]) / 2, "max_error_rate": 0.01}) == 1


def test_no_evidence_fails():
    checks = evaluate_load_test({"models": []}, _cfg())
    assert checks[0].status == FAIL and "stop_on_review_fail" in checks[0].detail


def test_collapsed_target_level_fails(tmp_path):
    root = tmp_path / "logs"
    write_run(root, "p", "m", 10, 1_000.0, ts="20261104-100000")
    write_run(root, "p", "m", 30, 2_000.0, ts="20261104-100100")
    write_run(root, "p", "m", 60, 3_000.0, failed_users=60, ts="20261104-100200")
    s = summarize(read_runs(root, "p"))
    st = {c.id: c.status for c in evaluate_load_test(s, load_config({"load_test": {"target_level": 60, "p95_sec": 10, "p50_sec": 10}}))}
    assert st["load_test.m.collapsed"] == FAIL and st["load_test.m.errors"] == FAIL


def test_rows_with_status_error_are_failed_and_out_of_the_percentiles(tmp_path):
    root = tmp_path / "logs"
    write_run(root, "p", "m", 4, 1_000.0, failed_query_every=4, ts="20261104-100000")
    lv = summarize(read_runs(root, "p"))["models"][0]["levels"][0]
    assert lv["recorded_queries"] == 12 and lv["errored_queries"] == 3 and lv["failed_queries"] == 3
    assert lv["queries"] == 9 and lv["error_rate"] == 0.25
    assert lv["max"] < 30, "the 30 s of a failed query must not reach the percentiles"
    assert lv["error_samples"][0].startswith("AdomdErrorResponseException") and "<upn>" in lv["error_samples"][0]


def test_failed_queries_and_lost_users_add_up(tmp_path):
    root = tmp_path / "logs"
    write_run(root, "p", "m", 4, 1_000.0, failed_query_every=4, failed_users=1, ts="20261104-100000")
    lv = summarize(read_runs(root, "p"))["models"][0]["levels"][0]
    assert lv["expected_queries"] == 12 and lv["errored_queries"] == 2 and lv["failed_queries"] == 3 + 2  # 3 of the lost user + 2 errored rows


def test_csv_files_before_orchestrator_3_3_have_no_status(tmp_path):
    root = tmp_path / "logs"
    write_run(root, "p", "m", 2, 1_000.0, legacy=True, ts="20261104-100000")
    lv = summarize(read_runs(root, "p"))["models"][0]["levels"][0]
    assert lv["queries"] == lv["recorded_queries"] == 6 and lv["failed_queries"] == 0


def test_growth_below_the_noise_floor_is_not_a_warning(logs):
    s = summarize(read_runs(logs, "gate-r1"))
    top_p95 = s["models"][0]["levels"][-1]["p95"]
    noisy = {c.id: c for c in evaluate_load_test(s, _cfg(max_p95_growth_ratio=1.0, min_p95_sec_for_growth_check=top_p95 + 1))}
    assert noisy["load_test.ventas.scalability"].status == PASS
    assert "no se evalúa" in noisy["load_test.ventas.scalability"].detail
    real = {c.id: c.status for c in evaluate_load_test(s, _cfg(max_p95_growth_ratio=1.0, min_p95_sec_for_growth_check=0))}
    assert real["load_test.ventas.scalability"] == WARN
