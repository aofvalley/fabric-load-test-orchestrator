import json

from promotion_gate import cli


def test_evaluate_offline_exit_codes(tmp_path, logs, review_ok, capacity_ok):
    (tmp_path / "r.json").write_text(json.dumps(review_ok), encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps(capacity_ok), encoding="utf-8")
    cfg = tmp_path / "gate.json"
    cfg.write_text(json.dumps({"load_test": {"target_level": 10, "p95_sec": 10, "p50_sec": 10, "max_p95_growth_ratio": 5}}))
    args = ["evaluate", "--review", str(tmp_path / "r.json"), "--logs", str(logs), "--run-prefix", "gate-r1",
            "--capacity", str(tmp_path / "c.json"), "--config", str(cfg), "--out", str(tmp_path / "out")]
    assert cli.main(args) == 0
    assert json.loads((tmp_path / "out" / "verdict.json").read_text(encoding="utf-8"))["verdict"] == "PASS"
    assert (tmp_path / "out" / "report.md").exists()
    assert cli.main(["evaluate", "--review", str(tmp_path / "r.json"), "--out", str(tmp_path / "o2")]) == 2


def test_default_config_file_loads():
    from promotion_gate.config import load_config

    cfg = load_config(str(cli.ROOT / "config" / "gate.yaml"))
    assert cfg["load_test"]["target_level"] == 60 and cfg["capacity"]["required"] is True
    assert "Do not use floating point data types" in cfg["model_review"]["blocking_rules"]


def test_build_notebooks_injects_wheel(tmp_path):
    wheel = tmp_path / "promotion_gate-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"x")
    assert cli.main(["build-notebooks", "--wheel", str(wheel), "--out", str(tmp_path / "nb")]) == 0
    text = (tmp_path / "nb" / "NB_Gate_ModelReview.ipynb").read_text(encoding="utf-8")
    assert "/lakehouse/default/Files/PromotionGate/lib/promotion_gate-0.1.0-py3-none-any.whl" in text
    assert "{{GATE_WHEEL}}" not in text


def test_promote_refuses_non_promotable_and_foreign_item(tmp_path):
    v = tmp_path / "v.json"
    v.write_text(json.dumps({"verdict": "FAIL", "promotable": False, "context": {"item_id": "m1"}}))
    base = ["promote", "--verdict", str(v), "--deployment-pipeline-id", "dp", "--source-stage-id", "s0",
            "--target-stage-id", "s1", "--dry-run"]
    assert cli.main(base) == 2
    v.write_text(json.dumps({"verdict": "PASS", "promotable": True, "context": {"item_id": "m1", "run_id": "r"}}))
    assert cli.main(base) == 0
    assert cli.main(base + ["--item-id", "otro"]) == 1


def test_override_is_layered_over_the_team_file(tmp_path):
    from promotion_gate.config import load_config

    team = tmp_path / "gate.yaml"
    team.write_text("load_test:\n  p95_sec: 3.0\n  target_level: 40\nmodel_review:\n  sku: F32\n", encoding="utf-8")
    cfg = load_config(str(team), override='{"load_test": {"target_level": 100}}')
    assert cfg["load_test"]["target_level"] == 100 and cfg["load_test"]["p95_sec"] == 3.0
    assert cfg["model_review"]["sku"] == "F32" and cfg["capacity"]["required"] is True
    assert load_config(str(tmp_path / "missing.yaml"))["load_test"]["target_level"] == 60


def test_string_parameters_stay_strings():
    out = cli.coerce_to_pipeline_types({"gate_config": {"load_test": {"target_level": 10}}, "ramp_levels": [1, 5], "iterations": 1})
    assert out["gate_config"] == '{"load_test": {"target_level": 10}}'
    assert out["ramp_levels"] == [1, 5] and out["iterations"] == 1


def test_notebook_params_send_objects_as_json_text():
    from promotion_gate.cli import _typed
    typed = _typed({"gate_config": {"load_test": {"target_level": 10}}, "max_extra_wait_minutes": 0, "flag": True})
    assert typed["gate_config"] == {"value": '{"load_test": {"target_level": 10}}', "type": "string"}
    assert typed["max_extra_wait_minutes"] == {"value": 0, "type": "int"}
    assert typed["flag"] == {"value": True, "type": "bool"}


def test_orchestrator_repo_defaults_to_the_repo_that_contains_the_gate(tmp_path, monkeypatch):
    import pytest
    from promotion_gate import cli
    gate = tmp_path / "orchestrator" / "promotion-gate"
    gate.mkdir(parents=True)
    monkeypatch.setattr(cli, "ROOT", gate)
    with pytest.raises(SystemExit, match="indica --repo"):
        cli.orchestrator_repo(None)
    (tmp_path / "orchestrator" / "notebooks").mkdir()
    (tmp_path / "orchestrator" / "notebooks" / "RunLoadTest_v3.ipynb").write_text("{}")
    assert cli.orchestrator_repo(None) == tmp_path / "orchestrator"
    with pytest.raises(SystemExit, match="no es un clon"):
        cli.orchestrator_repo(str(tmp_path))
