from promotion_gate.config import load_config
from promotion_gate.loadtest import read_runs, summarize
from promotion_gate.report import render_markdown
from promotion_gate.verdict import decide


def _cfg():
    return load_config({"load_test": {"target_level": 10, "p95_sec": 10, "p50_sec": 10, "max_p95_growth_ratio": 5}})


def test_all_green_is_promotable(logs, review_ok, capacity_ok):
    v = decide(review_ok, summarize(read_runs(logs, "gate-r1")), capacity_ok, _cfg(), {"run_id": "r1", "dataset": "Ventas"})
    assert v["verdict"] == "PASS" and v["promotable"]
    assert set(v["areas"]) == {"model_review", "load_test", "capacity"}


def test_warn_promotes_unless_configured(logs, review_ok, capacity_ok):
    cap = dict(capacity_ok, peak_interactive_delay_pct=85.0)
    v = decide(review_ok, summarize(read_runs(logs, "gate-r1")), cap, _cfg())
    assert v["verdict"] == "WARN" and v["promotable"]
    strict = load_config({**_cfg(), "verdict": {"warn_blocks_promotion": True}})
    assert not decide(review_ok, summarize(read_runs(logs, "gate-r1")), cap, strict)["promotable"]


def test_missing_evidence_blocks(review_ok):
    v = decide(review_ok, None, None, _cfg())
    assert v["verdict"] == "FAIL" and not v["promotable"]
    assert v["areas"]["load_test"] == "FAIL" and v["areas"]["capacity"] == "FAIL"


def test_report_contains_sections_and_advice(logs, review_ok, capacity_ok):
    cfg = load_config({"load_test": {"target_level": 10, "p95_sec": 1.0, "slow_query_sec": 1.0}})
    summary = summarize(read_runs(logs, "gate-r1"), slow_query_sec=1.0)
    v = decide(review_ok, summary, capacity_ok, cfg, {"run_id": "r1", "dataset": "Ventas"})
    md = render_markdown(v, review_ok, summary, capacity_ok)
    assert "# Gate de promoción: Ventas" in md and "❌ FAIL" in md
    for section in ("## Comprobaciones", "## Mejoras recomendadas", "## Test de carga", "## Capacity Metrics",
                    "## Revisión del modelo", "## Límites de la evidencia"):
        assert section in md
    assert "se degrada con la concurrencia" in md and "Usa DIVIDE()" in md
    assert "·" not in md


def test_advice_flags_client_bottleneck_when_capacity_is_idle(logs, review_ok, capacity_ok):
    cfg = load_config({"load_test": {"target_level": 10, "p95_sec": 1.0}})
    idle = dict(capacity_ok, peak_utilization_pct=20.0, peak_interactive_delay_pct=5.0)
    v = decide(review_ok, summarize(read_runs(logs, "gate-r1")), idle, cfg)
    assert any("capacidad holgada" in a["title"] for a in v["advice"])


def test_phases_not_run_after_failed_review_are_skipped_not_failed(review_ok):
    review = dict(review_ok, findings=review_ok["findings"] + [
        {"rule": "Avoid floating point", "category": "Performance", "severity": "Error", "object_type": "Column",
         "object_name": "'Ventas'[Importe]", "description": "", "url": ""}])
    v = decide(review, None, None, _cfg())
    assert v["verdict"] == "FAIL" and not v["promotable"]
    assert v["areas"] == {"model_review": "FAIL", "load_test": "SKIP", "capacity": "SKIP"}


def test_missing_load_test_after_passing_review_still_fails(review_ok):
    assert decide(review_ok, None, None, _cfg())["areas"]["load_test"] == "FAIL"
