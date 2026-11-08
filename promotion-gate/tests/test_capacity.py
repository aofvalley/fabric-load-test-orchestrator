from datetime import date, datetime, timezone

import pytest

from promotion_gate.capacity import (analyze, days_in_window, detect_version, evaluate_capacity, item_operation_query,
                                     norm_key, percent_scale, timepoints_query)
from promotion_gate.checks import FAIL, PASS, SKIP, WARN
from promotion_gate.config import load_config

CAP = "0f0f0f0f-1111-2222-3333-444444444444"
MODEL = "11111111-2222-3333-4444-555555555555"
TOOLS_WS = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_queries_follow_fuam_names_per_version():
    q53 = timepoints_query("v53", CAP, date(2026, 11, 4))
    assert "MPARAMETER 'CapacitiesList'" in q53 and "TREATAS({DATE(2026, 11, 4)}, 'Dates'[Date])" in q53
    assert "'All Measures'[Dynamic interactive delay %]" in q53
    q47 = timepoints_query("v47", CAP, date(2026, 11, 4))
    assert "FILTER(TimePoints, 'TimePoints'[Date] = DATE(2026, 11, 4))" in q47
    assert "MPARAMETER 'CapacityID'" in timepoints_query("v40", CAP, date(2026, 11, 4))
    io = item_operation_query("v53", CAP, date(2026, 11, 4))
    assert "'Metrics By Item Operation And Day'[CU (s)]" in io and "Capacities[Capacity Id] = " in io
    assert "Capacities[capacity Id] = " in item_operation_query("v47", CAP, date(2026, 11, 4))


def test_capacity_id_cannot_inject_dax():
    with pytest.raises(ValueError):
        timepoints_query("v53", 'x" } EVALUATE Items //', date(2026, 11, 4))
    with pytest.raises(ValueError):
        timepoints_query("v37", CAP, date(2026, 11, 4))


def test_detect_version_uses_first_probe_that_answers():
    calls = []

    def evaluate(dax):
        calls.append(dax)
        if "Blocked workspaces" in dax:
            raise RuntimeError("no existe")
        return []

    assert detect_version(evaluate) == "v47" and len(calls) == 2


def test_norm_key_and_days():
    assert norm_key("Capacities[capacity Id]") == "capacity Id" and norm_key("[B_P]") == "B_P"
    assert days_in_window("2026-11-04T23:50:00Z", "2026-11-05T00:20:00Z") == [date(2026, 11, 4), date(2026, 11, 5)]


def _tp(minute, b, i, delay=0.1, scale=1.0, sku=1.0):
    return {"TimePoints[TimePoint]": datetime(2026, 11, 4, 10, minute, tzinfo=timezone.utc).isoformat(),
            "[B_P]": b * scale, "[I_P]": i * scale, "[AS_P]": sku * scale, "[I_Del_P]": delay * scale,
            "[I_Rej_P]": 0.0, "[B_Rej_P]": 0.0, "[CO_C_P]": 0.0}


def test_percent_scale_detects_fraction_or_percent():
    assert percent_scale([{"AS_P": 1.0}, {"AS_P": 1.0}]) == 100.0
    assert percent_scale([{"AS_P": 100.0}]) == 1.0


def _ios():
    return [
        {"Items[Workspace Id]": "w", "Metrics By Item Operation And Day[Item Id]": MODEL, "Items[Item Kind]": "SemanticModel",
         "Metrics By Item Operation And Day[Operation name]": "Query", "[S_CU]": 800.0, "[S_Dur]": 200.0, "[C_O]": 400,
         "[C_FO]": 2, "[C_RO]": 0, "[TH_M]": 0.0},
        {"Items[Workspace Id]": TOOLS_WS, "Metrics By Item Operation And Day[Item Id]": "nb", "Items[Item Kind]": "Notebook",
         "Metrics By Item Operation And Day[Operation name]": "Notebook run", "[S_CU]": 1200.0, "[S_Dur]": 1.0, "[C_O]": 10,
         "[C_FO]": 0, "[C_RO]": 0, "[TH_M]": 0.0},
    ]


def test_analyze_filters_window_and_splits_model_and_tooling():
    tps = [_tp(0, 0.1, 0.1), _tp(10, 0.3, 0.6, delay=0.9), _tp(20, 0.2, 0.2), _tp(50, 0.9, 0.9)]
    m = analyze(tps, _ios(), {"start_utc": "2026-11-04T10:08:00Z", "end_utc": "2026-11-04T10:16:00Z"},
                MODEL, TOOLS_WS, margin_min=5, version="v53", capacity_id=CAP)
    assert m["timepoints_in_window"] == 2 and m["peak_utilization_pct"] == 90.0
    assert m["peak_interactive_delay_pct"] == 90.0
    assert m["model"]["cu_s"] == 800.0 and m["model"]["failed_operations"] == 2
    assert m["model"]["operations"][0]["cu_s_per_operation"] == 2.0
    assert m["tooling"]["share_pct"] == 60.0
    st = {c.id: c.status for c in evaluate_capacity(m, load_config())}
    assert st["capacity.utilization"] == FAIL and st["capacity.interactive_delay"] == WARN
    assert st["capacity.model_operations"] == FAIL and st["capacity.tooling_share"] == WARN


def test_percent_values_are_not_rescaled():
    m = analyze([_tp(10, 0.3, 0.2, scale=100.0)], [], {"start_utc": "2026-11-04T10:09:00Z", "end_utc": "2026-11-04T10:11:00Z"}, MODEL)
    assert m["peak_utilization_pct"] == 50.0


def test_missing_capacity_evidence(capacity_ok):
    cfg = load_config()
    assert evaluate_capacity(None, cfg)[0].status == FAIL
    assert evaluate_capacity({"error": "x"}, load_config({"capacity": {"required": False}}))[0].status == SKIP
    empty = dict(capacity_ok, timepoints_in_window=0)
    assert "metrics_lag_minutes" in evaluate_capacity(empty, cfg)[0].detail
    assert all(c.status == PASS for c in evaluate_capacity(capacity_ok, cfg))


def test_partial_metrics_that_miss_test_end_fail():
    tps = [_tp(0, 0.1, 0.1), _tp(10, 0.2, 0.2)]
    m = analyze(tps, [], {"start_utc": "2026-11-04T10:00:00Z", "end_utc": "2026-11-04T10:30:00Z"}, MODEL)
    assert m["covers_window_end"] is False and m["timepoints_in_window"] == 2
    checks = evaluate_capacity(m, load_config())
    assert checks[0].status == FAIL and "incompleto" in checks[0].title


def test_v53_column_casing_is_understood():
    """Capacity Metrics v53 (tenant real) devuelve 'Timepoints[Timepoint]' e 'Items[Item kind]'."""
    tps = [{"Timepoints[Timepoint]": "2026-11-05T10:44:00", "[B_P]": 0.2, "[I_P]": 0.1},
           {"Timepoints[Timepoint]": "2026-11-05T10:50:00", "[B_P]": 0.1, "[I_P]": 0.0}]
    ios = [{"Items[Workspace Id]": "W", "Metrics By Item Operation And Day[Item Id]": "M",
            "Items[Item kind]": "SemanticModel", "Metrics By Item Operation And Day[Operation name]": "Query",
            "[S_CU]": 3.0, "[C_O]": 2}]
    m = analyze(tps, ios, {"start_utc": "2026-11-05T10:44:21Z", "end_utc": "2026-11-05T10:47:43Z"}, "m")
    assert m["timepoints_in_window"] == 2 and m["covers_window_end"]
    assert m["peak_utilization_pct"] == 30.0 and m["model"]["found"]


def test_model_missing_from_stale_daily_table_is_pending_not_warning(capacity_ok):
    cfg = load_config()
    stale = {**capacity_ok, "model": {**capacity_ok["model"], "found": False, "operations": []},
             "tooling": {"workspace_id": "T", "cu_s": 0, "found": False, "share_pct": 0.0}}
    found = {c.id: c.status for c in evaluate_capacity(stale, cfg)}
    assert found["capacity.model_found"] == SKIP
    fresh = {**stale, "tooling": {**stale["tooling"], "found": True}}
    assert {c.id: c.status for c in evaluate_capacity(fresh, cfg)}["capacity.model_found"] == WARN


def test_timepoints_in_the_app_local_time_are_converted_to_utc():
    """La app instalada con UTC+2 etiqueta 14:05 lo que en UTC son las 12:05."""
    from promotion_gate.capacity import parse_utc_offset
    offset = parse_utc_offset([{"Latest Summary Timestamp[endTime]": "2026-11-06T12:16:30",
                                "Latest Summary Timestamp[UTC Offset]": 2.0}])
    assert offset == 2.0
    tps = [{"Timepoints[Timepoint]": "2026-11-06T14:05:00", "[B_P]": 0.3, "[I_P]": 0.1},
           {"Timepoints[Timepoint]": "2026-11-06T12:05:00", "[B_P]": 0.0, "[I_P]": 0.0}]
    window = {"start_utc": "2026-11-06T12:02:00Z", "end_utc": "2026-11-06T12:10:00Z"}
    m = analyze(tps, [], window, "m", utc_offset_hours=offset)
    assert m["timepoints_in_window"] == 1 and m["peak_utilization_pct"] == 40.0
    assert m["latest_timepoint_utc"].startswith("2026-11-06T12:05") and m["utc_offset_hours"] == 2.0
    assert analyze(tps, [], window, "m")["peak_utilization_pct"] == 0.0


def test_days_follow_the_app_local_time():
    from promotion_gate.capacity import parse_utc_offset
    assert days_in_window("2026-11-06T23:00:00Z", "2026-11-06T23:30:00Z", 2.0) == [date(2026, 11, 7)]
    assert days_in_window("2026-11-06T23:00:00Z", "2026-11-06T23:30:00Z") == [date(2026, 11, 6)]
    assert parse_utc_offset([]) == 0.0


def test_hourly_operations_query_covers_the_test_hours_in_local_time():
    from datetime import datetime
    from promotion_gate.capacity import item_operation_hour_query
    dax = item_operation_hour_query("v53", "11111111-2222-3333-4444-555555555555",
                                    datetime(2026, 11, 6, 14, 2), datetime(2026, 11, 6, 15, 10))
    assert "'Metrics By Item Operation And Hour'[Datetime] >= DATE(2026, 11, 6) + TIME(14, 0, 0)" in dax
    assert "<= DATE(2026, 11, 6) + TIME(15, 0, 0)" in dax
    assert '"C_FO", SUM(' in dax and "MPARAMETER 'CapacitiesList'" in dax
    with pytest.raises(ValueError):
        item_operation_hour_query("v47", "11111111-2222-3333-4444-555555555555", datetime(2026, 1, 1), datetime(2026, 1, 1))


def test_operations_scope_is_reported(capacity_ok):
    cfg = load_config()
    hour = {**capacity_ok, "operations_scope": "hour",
            "model": {**capacity_ok["model"], "found": True, "failed_operations": 0, "rejected_operations": 0}}
    detail = {c.id: c.detail for c in evaluate_capacity(hour, cfg)}
    assert "horas del test" in detail["capacity.model_operations"]
