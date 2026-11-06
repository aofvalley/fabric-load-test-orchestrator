from promotion_gate.bpa import (columns_from_sempy, evaluate_model_review, normalize_findings, normalize_severity,
                                summarize_vertipaq, tables_from_sempy)
from promotion_gate.checks import FAIL, PASS, SKIP, WARN
from promotion_gate.config import load_config


def test_severity_icons_from_semantic_link_labs():
    assert normalize_severity("\u274c") == "Error"
    assert normalize_severity("\u26a0\ufe0f") == "Warning"
    assert normalize_severity("\u2139\ufe0f") == "Info"
    assert normalize_severity("Warning") == "Warning"


def test_normalize_findings_from_dataframe_records():
    rows = [{"Category": "Performance", "Rule Name": "Do not use floating point data types", "Object Type": "Column",
             "Object Name": "'Hechos'[Importe]", "Severity": "\u26a0\ufe0f", "Description": "d", "URL": "u"}]
    f = normalize_findings(rows)[0]
    assert f == {"rule": "Do not use floating point data types", "category": "Performance", "severity": "Warning",
                 "object_type": "Column", "object_name": "'Hechos'[Importe]", "description": "d", "url": "u"}


def test_blocking_rule_fails_even_if_warning():
    cfg = load_config({"model_review": {"blocking_rules": ["Do not use floating point data types"]}})
    review = {"findings": normalize_findings([{"Rule Name": "Do not use floating point data types", "Severity": "Warning",
                                               "Object Name": "x"}])}
    st = {c.id: c.status for c in evaluate_model_review(review, cfg)}
    assert st["model_review.blocking_rules"] == FAIL and st["model_review.bpa_errors"] == PASS


def test_ignored_rules_are_excluded():
    cfg = load_config({"model_review": {"max_errors": 0, "ignored_rules": ["Rule X"]}})
    review = {"findings": [{"rule": "Rule X", "severity": "Error", "category": "", "object_name": "a"}]}
    assert {c.id: c.status for c in evaluate_model_review(review, cfg)}["model_review.bpa_errors"] == PASS


def test_memory_against_sku_limit():
    cfg = load_config({"model_review": {"sku": "F8"}})  # 3 GB por modelo
    review = {"findings": [], "vertipaq": {"model_size_mb": 2048.0, "top_columns": []}}
    checks = {c.id: c for c in evaluate_model_review(review, cfg)}
    assert checks["model_review.memory"].status == WARN and checks["model_review.memory"].evidence["pct_of_sku_limit"] > 60


def test_missing_or_errored_review_fails():
    cfg = load_config()
    assert evaluate_model_review(None, cfg)[0].status == FAIL
    assert evaluate_model_review({"error": "boom"}, cfg)[0].status == FAIL


def test_without_vertipaq_memory_is_skipped():
    st = {c.id: c.status for c in evaluate_model_review({"findings": []}, load_config())}
    assert st["model_review.memory"] == SKIP


def test_vertipaq_summary_from_sempy_frames():
    cols = columns_from_sempy([
        {"Table Name": "Hechos", "Column Name": "Id", "Total Size": 600 * 1024 * 1024, "Column Cardinality": 9, "Data Type": "String"},
        {"Table Name": "Hechos", "Column Name": "Fecha", "Total Size": 100 * 1024 * 1024, "Column Cardinality": 3, "Data Type": "DateTime"},
    ])
    tabs = tables_from_sempy([{"Name": "Hechos", "Row Count": 10, "Total Size": 1024 * 1024 * 1024}])
    vp = summarize_vertipaq(sum(t["size_bytes"] for t in tabs), cols, tabs)
    assert vp["model_size_mb"] == 1024.0
    assert vp["top_columns"][0]["column"] == "Id" and vp["top_columns"][0]["pct_of_model"] == 58.6
    heavy = {c.id: c.status for c in evaluate_model_review({"findings": [], "vertipaq": vp}, load_config())}
    assert heavy["model_review.heavy_columns"] == WARN


def test_small_models_skip_the_heavy_column_check():
    vp = {"model_size_mb": 0.8, "top_columns": [{"table": "V", "column": "Importe", "size_mb": 0.3, "pct_of_model": 31.7}]}
    checks = {c.id: c for c in evaluate_model_review({"findings": [], "vertipaq": vp}, load_config())}
    assert checks["model_review.heavy_columns"].status == PASS and "no se evalúa" in checks["model_review.heavy_columns"].detail


def test_warmup_touches_every_column_once_per_table():
    from promotion_gate.bpa import warmup_queries
    qs = warmup_queries([{"table": "Ventas", "column": "Importe"}, {"table": "Ventas", "column": "Fecha clave"},
                         {"table": "Ventas", "column": "RowNumber-2662979B"}, {"table": "O'Brien", "column": "a]b"}])
    assert qs == ['EVALUATE ROW("c0", DISTINCTCOUNT(\'Ventas\'[Importe]), "c1", DISTINCTCOUNT(\'Ventas\'[Fecha clave]))',
                  'EVALUATE ROW("c0", DISTINCTCOUNT(\'O\'\'Brien\'[a]]b]))']
