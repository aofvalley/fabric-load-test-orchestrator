"""Unit tests of the think-time helpers embedded in RunPerfScenario_v3 (calculation, validation and the Performance Analyzer parser)."""
import ast
import json
import types

import pytest

import make_sample_data as sample_data
from helpers import NOTEBOOKS, SAMPLE, UPSTREAM, find_cell, load_notebook


@pytest.fixture(scope="module")
def helpers():
    namespace = {}
    source = find_cell(load_notebook(NOTEBOOKS / "RunPerfScenario_v3.ipynb"), "def calculate_applied_think_time")
    exec(compile(source, "think-time-helpers", "exec"), namespace)
    return types.SimpleNamespace(**namespace)


# ---------------------------------------------------------------------------------- event builders
def write_events(tmp_path, events):
    path = tmp_path / "performance.json"
    path.write_text(json.dumps({"version": "1.1.0", "events": events}), encoding="utf-8")
    return str(path)


def action(start, label="UserAction_X", end=None):
    event = {"name": "User Action", "start": start, "metrics": {"sourceLabel": label}}
    if end:
        event["end"] = end
    return event


def visual(title="V", visual_id="v1"):
    return {"name": "Visual Container Lifecycle", "start": "2026-01-01T00:00:00.000Z", "metrics": {"visualTitle": title, "visualId": visual_id}}


def dax(start, end, text="EVALUATE 1"):
    return {"name": "Execute DAX Query", "start": start, "end": end, "metrics": {"QueryText": text}}


# --------------------------------------------------------------------------- calculate_applied_think_time
@pytest.mark.parametrize("original, enabled, scale, maximum, expected", [
    (10, True, 1.0, 60, 10),
    (10, True, 0.5, 60, 5),
    (10, True, 2.0, 60, 20),
    (10, True, 0.0, 60, 0),
    (100, True, 1.0, 60, 60),   # capped by max_think_time_sec
    (-5, True, 1.0, 60, 0),     # never negative
    (10, False, 1.0, 60, 0),    # disabled
    (None, True, 1.0, 60, 0),   # missing value
])
def test_calculate_applied_think_time(helpers, original, enabled, scale, maximum, expected):
    assert helpers.calculate_applied_think_time(original, enabled, scale, maximum, 0) == expected


def test_jitter_stays_within_bounds_and_never_creates_a_pause_from_nothing(helpers):
    values = [helpers.calculate_applied_think_time(10, True, 1.0, 60, 0.10) for _ in range(500)]
    assert all(9.0 <= v <= 11.0 for v in values)
    assert len(set(values)) > 1, "jitter should vary the pause"
    assert helpers.calculate_applied_think_time(0, True, 1.0, 60, 0.5) == 0


@pytest.mark.parametrize("arguments, message", [
    ((-1, 60, 0), "think_time_scale"),
    ((1, -1, 0), "max_think_time_sec"),
    ((1, 60, 1.5), "think_time_jitter_pct"),
    ((1, 60, -0.1), "think_time_jitter_pct"),
    ((1, 60, 0, -1), "cannot be negative"),
    ((1, 60, 0, 0, -1), "cannot be negative"),
    ((1, 60, 0, 0, 0, -1), "cannot be negative"),
])
def test_validate_think_time_params_rejects_bad_values(helpers, arguments, message):
    with pytest.raises(ValueError, match=message):
        helpers.validate_think_time_params(*arguments)


def test_validate_think_time_params_accepts_good_values(helpers):
    helpers.validate_think_time_params(1.0, 60.0, 0.1, 300.0, 10.0, 0.0)


# ------------------------------------------------------------------------------------------- the parser
def test_single_event_file(helpers, tmp_path):
    queries = helpers.load_queries(write_events(tmp_path, [dax("2026-01-01T00:00:05Z", "2026-01-01T00:00:06Z")]))
    assert len(queries) == 1
    assert queries[0]["think_time_before_sec"] == 0.0 and queries[0]["is_first_query_in_action"]


def test_file_without_user_actions_uses_the_fallback(helpers, tmp_path):
    events = [visual(), dax("2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z"), dax("2026-01-01T00:00:03Z", "2026-01-01T00:00:04Z")]
    path = write_events(tmp_path, events)
    assert [q["think_time_before_sec"] for q in helpers.load_queries(path, fallback_think_time_sec=0.0)] == [0.0, 0.0]
    with_fallback = helpers.load_queries(path, fallback_think_time_sec=2.5)
    assert [q["think_time_before_sec"] for q in with_fallback] == [0.0, 2.5]
    assert all(q["is_first_query_in_action"] for q in with_fallback)


def test_invalid_timestamps_never_produce_nan_or_negative_pauses(helpers, tmp_path):
    events = [action("not-a-date"), action("2026-01-01T00:00:10Z"), dax("garbage", None), dax("2026-01-01T00:00:11Z", "invalid"), dax(None, None)]
    queries = helpers.load_queries(write_events(tmp_path, events))
    assert len(queries) == 3
    for q in queries:
        value = q["think_time_before_sec"]
        assert value == value and value >= 0.0


def test_several_queries_of_one_action_produce_a_single_pause(helpers, tmp_path):
    events = [action("2026-01-01T00:00:00Z"),
              dax("2026-01-01T00:00:00.100Z", "2026-01-01T00:00:01Z"), dax("2026-01-01T00:00:00.200Z", "2026-01-01T00:00:02Z"),
              action("2026-01-01T00:00:10Z"),
              dax("2026-01-01T00:00:10.100Z", "2026-01-01T00:00:11Z"), dax("2026-01-01T00:00:10.200Z", "2026-01-01T00:00:12Z")]
    queries = helpers.load_queries(write_events(tmp_path, events), group_by_action=True)
    assert [q["is_first_query_in_action"] for q in queries] == [True, False, True, False]
    assert queries[0]["think_time_before_sec"] == 0.0
    assert queries[2]["think_time_before_sec"] == queries[3]["think_time_before_sec"] == 8.0
    assert queries[2]["think_time_basis"] == "previous_group_end"


def test_two_actions_with_the_same_timestamp(helpers, tmp_path):
    events = [action("2026-01-01T00:00:00Z"), action("2026-01-01T00:00:00Z", "UserAction_Y"), dax("2026-01-01T00:00:00.500Z", "2026-01-01T00:00:01Z")]
    queries = helpers.load_queries(write_events(tmp_path, events), group_by_action=True)
    assert len(queries) == 1 and queries[0]["think_time_before_sec"] == 0.0


def test_an_explicit_action_end_is_used_when_present(helpers, tmp_path):
    events = [action("2026-01-01T00:00:00Z", end="2026-01-01T00:00:03Z"), dax("2026-01-01T00:00:00.5Z", "2026-01-01T00:00:01Z"),
              action("2026-01-01T00:00:10Z"), dax("2026-01-01T00:00:10.5Z", "2026-01-01T00:00:11Z")]
    queries = helpers.load_queries(write_events(tmp_path, events), group_by_action=True)
    assert queries[1]["think_time_before_sec"] == 7.0


def test_labels_and_event_order_are_arbitrary(helpers, tmp_path):
    events = [action("2026-01-01T00:00:20Z", "UserAction_Drill"), action("2026-01-01T00:00:00Z", "UserAction_Whatever"),
              dax("2026-01-01T00:00:21Z", "2026-01-01T00:00:22Z"), dax("2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z")]
    queries = helpers.load_queries(write_events(tmp_path, events), group_by_action=True)
    assert [q["action_label"] for q in queries] == ["UserAction_Whatever", "UserAction_Drill"]
    assert queries[1]["think_time_before_sec"] == 18.0


def test_queries_before_the_first_action_and_actions_without_queries(helpers, tmp_path):
    events = [dax("2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"),
              action("2026-01-01T00:00:05Z", "Without_queries"),
              action("2026-01-01T00:00:15Z", "With_queries"), dax("2026-01-01T00:00:16Z", "2026-01-01T00:00:17Z")]
    queries = helpers.load_queries(write_events(tmp_path, events), group_by_action=True)
    assert [q["action_label"] for q in queries] == ["PreAction", "With_queries"]
    assert queries[1]["think_time_before_sec"] == 14.0


# ------------------------------------------------------------------------------------------ sample file
def test_sample_file_is_grouped_in_five_actions_with_the_expected_pauses(helpers):
    queries = helpers.load_queries(str(SAMPLE), group_by_action=True)
    assert len(queries) == sum(len(a[2]) for a in sample_data.ACTIONS) == 11
    firsts = [q for q in queries if q["is_first_query_in_action"]]
    assert [q["action_query_count"] for q in firsts] == [len(a[2]) for a in sample_data.ACTIONS]
    assert [q["action_label"] for q in firsts] == [a[0] for a in sample_data.ACTIONS]
    for q, expected in zip(firsts, sample_data.EXPECTED_THINK_TIMES):
        assert q["think_time_before_sec"] == pytest.approx(expected, abs=0.001)


def test_the_default_mode_keeps_the_order_and_content_of_the_original_load_queries(helpers):
    """With group_by_action=False the result must match the load_queries() of the upstream RunPerfScenario notebook."""
    upstream_cell = find_cell(load_notebook(UPSTREAM / "RunPerfScenario.ipynb"), "def load_queries")
    function = next(n for n in ast.parse(upstream_cell).body if isinstance(n, ast.FunctionDef) and n.name == "load_queries")
    namespace = {"json": json}
    exec(ast.get_source_segment(upstream_cell, function), namespace)
    original = namespace["load_queries"](str(SAMPLE))
    ours = helpers.load_queries(str(SAMPLE))
    assert len(original) == len(ours) == 11
    for a, b in zip(original, ours):
        assert (a["visual_name"], a["visual_id"], a["query_text"]) == (b["visual_name"], b["visual_id"], b["query_text"])
