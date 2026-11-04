"""Tests of AnalyzeLoadTest_v3: it runs against CSV files produced by the real RunPerfScenario_v3 notebook (fake ADOMD connection)."""
import shutil
import threading

import pytest

pd = pytest.importorskip("pandas")
duckdb = pytest.importorskip("duckdb")

import make_sample_data as sample_data
from helpers import NOTEBOOKS, SAMPLE, code_cells, install_fake_fabric_modules, load_notebook, run_scenario_user

MODELS = ["Sales", "Inventory"]
LEVELS = [(3, 0.0), (6, 1.2)]  # (concurrent users, ramp_up_sec)
ITERATIONS = 2
SCALE = 0.03
QUERIES_PER_ITERATION = sum(len(a[2]) for a in sample_data.ACTIONS)
ACTIONS = len(sample_data.ACTIONS)
LOGS_DEFAULT = "/lakehouse/default/Files/PerfScenarios/logs"


def run_user(root, run_id, model, thread_id, level, ramp_up):
    run_scenario_user(root, perf_analyzer_filename=str(SAMPLE), loadtestId=run_id, load_test_name=run_id, threadId=thread_id,
                      concurrent_threads=level, effective_username=None, model=model, workspace="ws", customdata=None,
                      iterations=ITERATIONS, delay_sec=0.01, enable_think_times=True, think_time_scale=SCALE,
                      max_think_time_sec=60.0, think_time_jitter_pct=0.1, start_delay_sec=ramp_up * thread_id / level,
                      initial_user_jitter_sec=0.0)


def run_model(root, model):
    """The sequential ramp of one model: every level waits for the previous one, like the Ramp pipeline does."""
    for level, ramp_up in LEVELS:
        run_id = f"ramp-v3-{model}-c{level}-20260101-1200{level:02d}"
        users = [threading.Thread(target=run_user, args=(root, run_id, model, i, level, ramp_up)) for i in range(level)]
        for t in users:
            t.start()
        for t in users:
            t.join()


def execute_cells(cells, logs, replacements=None, display=None):
    namespace = {"display": display or (lambda frame: None)}
    setup = cells[0].replace(LOGS_DEFAULT, logs)
    for old, new in (replacements or {}).items():
        assert old in setup, old
        setup = setup.replace(old, new)
    exec(compile(setup, "analysis-setup", "exec"), namespace)
    for index, source in enumerate(cells[1:], start=1):
        exec(compile(source, f"analysis-query-{index}", "exec"), namespace)
    return namespace


@pytest.fixture(scope="module")
def run_data(tmp_path_factory):
    """Two models in parallel, each through a two-level sequential ramp."""
    root = tmp_path_factory.mktemp("lakehouse")
    errors = []

    def guarded(model):
        try:
            run_model(root, model)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    with pytest.MonkeyPatch.context() as patch:
        install_fake_fabric_modules(patch)
        threads = [threading.Thread(target=guarded, args=(m,)) for m in MODELS]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert not errors, errors
    return (root / "Files" / "PerfScenarios" / "logs").as_posix()


@pytest.fixture(scope="module")
def cells():
    found = code_cells(load_notebook(NOTEBOOKS / "AnalyzeLoadTest_v3.ipynb"))
    assert len(found) == 10  # setup + nine queries
    return found


@pytest.fixture(scope="module")
def frames(run_data, cells):
    shown = []
    execute_cells(cells, run_data, display=shown.append)
    assert len(shown) == 9
    return shown


def test_every_query_returns_rows(frames):
    for number, frame in enumerate(frames, start=1):
        assert len(frame) > 0, f"query {number} returned no rows"


def test_q1_one_run_per_model_and_level_with_the_expected_users(frames):
    frame = frames[0]
    assert sorted(zip(frame["model"], frame["level"])) == sorted((m, level) for m in MODELS for level, _ in LEVELS)
    assert frame["users_ok"].all()
    assert (frame["queries"] == frame["level"] * ITERATIONS * QUERIES_PER_ITERATION).all()


def test_q2_the_ramp_is_sequential_inside_each_model(frames):
    frame = frames[1]
    assert set(frame[frame["level"] == LEVELS[0][0]]["sequence"]) == {"OK: sequential"}
    assert set(frame[frame["level"] == LEVELS[1][0]]["sequence"]) == {"last level"}


def test_q3_concurrency_and_start_window(frames):
    frame = frames[2].set_index(["model", "level"])
    for model in MODELS:
        small, large = frame.loc[(model, LEVELS[0][0])], frame.loc[(model, LEVELS[1][0])]
        assert small["users"] == LEVELS[0][0] and small["peak_concurrent"] <= LEVELS[0][0]
        assert large["users"] == LEVELS[1][0] and 1 <= large["peak_concurrent"] <= LEVELS[1][0]
        expected_window = LEVELS[1][1] * (LEVELS[1][0] - 1) / LEVELS[1][0]  # ramp_up_sec x last index / users
        assert expected_window - 0.4 <= large["start_window_s"] <= expected_window + 0.6
        assert small["start_window_s"] < 0.5


def test_q4_every_user_ran_every_query_of_the_file(frames):
    frame = frames[3]
    assert (frame["min_queries_per_user_iteration"] == QUERIES_PER_ITERATION).all()
    assert (frame["max_queries_per_user_iteration"] == QUERIES_PER_ITERATION).all()
    assert (frame["min_actions"] == ACTIONS).all() and (frame["max_actions"] == ACTIONS).all()


def test_q5_think_times_match_the_configured_scale(frames):
    frame = frames[4]
    assert len(frame) == len(MODELS) * len(LEVELS)
    assert (frame["pauses_per_user_iteration"] == ACTIONS).all()
    assert (frame["scale"] == SCALE).all()
    assert (abs(frame["applied_to_original_ratio"] - SCALE) < SCALE * 0.15).all()  # jitter is +/-10 %


def test_q6_the_measured_wait_between_actions_matches_the_applied_think_time(frames):
    frame = frames[5]
    assert (frame["avg_deviation_s"] < 0.1).all(), frame.to_string()
    assert (abs(frame["avg_actual_pause_s"] - frame["avg_applied_pause_s"]) < 0.1).all()


def test_q7_one_user_action_by_action(frames):
    frame = frames[6]
    assert len(frame) == ACTIONS
    assert int(frame["queries"].sum()) == QUERIES_PER_ITERATION
    assert pd.isna(frame["actual_pause_s"].iloc[0]), "the first action has no previous action"
    assert list(frame["action"]) == [a[0] for a in sample_data.ACTIONS]


def test_q8_latency_percentiles_are_ordered(frames):
    frame = frames[7]
    assert len(frame) == len(MODELS) * len(LEVELS)
    assert ((frame["p50_s"] <= frame["p90_s"]) & (frame["p90_s"] <= frame["p95_s"]) & (frame["p95_s"] <= frame["max_s"])).all()


def test_q1_and_q8_have_no_failed_queries_in_a_clean_run(frames):
    assert (frames[0]["failed_queries"] == 0).all()
    assert (frames[7]["failed_queries"] == 0).all() and (frames[7]["error_rate"] == 0).all()


def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(header) + "\n" + "".join(",".join(map(str, r)) + "\n" for r in rows), encoding="utf-8")


def test_q8_excludes_failed_queries_and_old_runs_without_status_still_work(cells, tmp_path):
    base = ["loadtest_id", "model", "concurrent_threads", "thread_id", "iteration", "query_number", "action_index",
            "duration", "start_time"]
    logs = tmp_path / "logs"
    new = "ramp-v3-M-c1-20260101-120000"
    _write_csv(logs / new / f"{new}_user_0.csv", base + ["status", "error"],
               [[new, "M", 1, 0, 0, 1, 1, 1.0, 100, "ok", ""], [new, "M", 1, 0, 0, 2, 1, 30.0, 102, "error", "timeout"]])
    shown = []
    execute_cells([cells[0], cells[1], cells[8]], logs.as_posix(), display=shown.append)
    q1, q8 = shown
    assert q1["failed_queries"].iloc[0] == 1
    assert q8["failed_queries"].iloc[0] == 1 and q8["error_rate"].iloc[0] == 0.5 and q8["max_s"].iloc[0] == 1.0

    old_logs = tmp_path / "old"
    old = "ramp-v3-M-c1-20250101-120000"
    _write_csv(old_logs / old / f"{old}_user_0.csv", base, [[old, "M", 1, 0, 0, 1, 1, 2.0, 100]])
    shown = []
    execute_cells([cells[0], cells[8]], old_logs.as_posix(), display=shown.append)
    assert shown[0]["failed_queries"].iloc[0] == 0 and shown[0]["p50_s"].iloc[0] == 2.0


def test_q9_the_models_ran_in_parallel(frames):
    frame = frames[8]
    assert len(frame) >= 1 and (frame["overlap_s"] >= 0).all()


def test_the_notebook_warns_when_there_are_no_think_time_files(run_data, cells, capsys, tmp_path):
    copy = tmp_path / "logs"
    shutil.copytree(run_data, copy)
    for folder in copy.glob("*/thinktimes"):
        shutil.rmtree(folder)
    shown = []
    execute_cells(cells[:5], copy.as_posix(), display=shown.append)  # queries 1-4 do not need the think-time files
    assert "no think-time CSV files found" in capsys.readouterr().out
    assert len(shown) == 4


def test_a_filter_that_leaves_no_rows_fails_with_a_clear_message(run_data, cells):
    with pytest.raises(ValueError, match="No results"):
        execute_cells(cells, run_data, replacements={"SINCE_UTC = None": 'SINCE_UTC = "2999-01-01T00:00:00Z"'})


def test_missing_result_files_are_reported_by_duckdb(tmp_path, cells):
    with pytest.raises(duckdb.Error):
        execute_cells(cells, (tmp_path / "empty").as_posix())
