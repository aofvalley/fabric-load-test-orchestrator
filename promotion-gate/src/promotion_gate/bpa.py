"""Revisión del modelo: resultados del Best Practice Analyzer (semantic-link-labs) y estadísticas VertiPaq."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .checks import FAIL, PASS, SKIP, WARN, Check, n
from .config import SKU_MAX_MODEL_MEMORY_GB

_SEVERITY_ALIASES = {
    "error": "Error", "\u274c": "Error", "3": "Error",
    "warning": "Warning", "\u26a0\ufe0f": "Warning", "\u26a0": "Warning", "2": "Warning",
    "info": "Info", "\u2139\ufe0f": "Info", "\u2139": "Info", "1": "Info",
}


def normalize_severity(value: Any) -> str:
    text = str(value or "").strip()
    return _SEVERITY_ALIASES.get(text.lower(), _SEVERITY_ALIASES.get(text, "Info"))


def normalize_findings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte las filas de `sempy_labs.run_model_bpa(..., return_dataframe=True)` a un formato estable."""
    out = []
    for r in records or []:
        out.append({
            "rule": str(r.get("Rule Name") or r.get("rule") or "").strip(),
            "category": str(r.get("Category") or r.get("category") or "").strip(),
            "severity": normalize_severity(r.get("Severity", r.get("severity"))),
            "object_type": str(r.get("Object Type") or r.get("Scope") or r.get("object_type") or "").strip(),
            "object_name": str(r.get("Object Name") or r.get("object_name") or "").strip(),
            "description": str(r.get("Description") or r.get("description") or "").strip(),
            "url": str(r.get("URL") or r.get("url") or "").strip(),
        })
    return out


def _pick(row: dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return None


def columns_from_sempy(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas de `sempy.fabric.list_columns(extended=True)` a {table, column, size_bytes, cardinality, data_type}."""
    return [{
        "table": _pick(r, "Table Name", "Table"), "column": _pick(r, "Column Name", "Column"),
        "size_bytes": float(_pick(r, "Total Size", "Total Size (bytes)") or 0),
        "cardinality": _pick(r, "Cardinality", "Column Cardinality", "Distinct Count"),
        "data_type": _pick(r, "Data Type", "Type"),
    } for r in records or []]


def warmup_queries(columns: list[dict[str, Any]]) -> list[str]:
    """Una consulta por tabla que toca todas sus columnas. En Direct Lake las columnas no están en memoria hasta que
    alguien las consulta; sin esto VertiPaq mide 0 bytes y cardinalidad 1."""
    by_table: dict[str, list[str]] = {}
    for c in columns:
        t, col = c.get("table"), c.get("column")
        if t and col and not str(col).startswith("RowNumber-"):
            by_table.setdefault(str(t), []).append(str(col))
    q = lambda name: name.replace("'", "''")
    out = []
    for t, cols in by_table.items():
        parts = ", ".join(f'"c{i}", DISTINCTCOUNT(\'{q(t)}\'[{c.replace("]", "]]")}])' for i, c in enumerate(cols))
        out.append(f"EVALUATE ROW({parts})")
    return out


def tables_from_sempy(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas de `sempy.fabric.list_tables(extended=True)` a {name, rows, size_bytes}."""
    return [{"name": _pick(r, "Name", "Table Name"), "rows": _pick(r, "Row Count", "Rows"),
             "size_bytes": float(_pick(r, "Total Size", "Table Size") or 0)} for r in records or []]


def summarize_vertipaq(model_size_bytes: float | None, columns: list[dict[str, Any]] | None,
                       tables: list[dict[str, Any]] | None = None, top: int = 10) -> dict[str, Any]:
    """Resumen pequeño y serializable de VertiPaq: tamaño, columnas más pesadas y tablas más grandes."""
    columns = columns or []
    total = float(model_size_bytes or 0) or float(sum(float(c.get("size_bytes") or 0) for c in columns))
    cols = sorted(columns, key=lambda c: float(c.get("size_bytes") or 0), reverse=True)[:top]
    return {
        "model_size_mb": round(total / 1024 / 1024, 1) if total else None,
        "top_columns": [{
            "table": c.get("table"), "column": c.get("column"),
            "size_mb": round(float(c.get("size_bytes") or 0) / 1024 / 1024, 1),
            "pct_of_model": round(100.0 * float(c.get("size_bytes") or 0) / total, 1) if total else None,
            "cardinality": c.get("cardinality"), "data_type": c.get("data_type"),
        } for c in cols],
        "top_tables": [{"table": t.get("name") or t.get("table"), "rows": t.get("rows"),
                        "size_mb": round(float(t.get("size_bytes") or 0) / 1024 / 1024, 1)}
                       for t in sorted(tables or [], key=lambda t: float(t.get("size_bytes") or 0), reverse=True)[:top]],
    }


def evaluate_model_review(review: dict[str, Any] | None, cfg: dict[str, Any]) -> list[Check]:
    c = cfg["model_review"]
    if not review:
        return [Check("model_review.evidence", "model_review", FAIL, "Sin evidencia de la revisión del modelo",
                      "No existe model_review.json: el notebook NB_Gate_ModelReview no terminó.")]
    if review.get("error"):
        return [Check("model_review.evidence", "model_review", FAIL, "La revisión del modelo falló", str(review["error"]))]

    ignored = {r.lower() for r in c.get("ignored_rules", [])}
    findings = [f for f in review.get("findings", []) if f["rule"].lower() not in ignored]
    counts = Counter(f["severity"] for f in findings)
    checks: list[Check] = []

    errors = counts.get("Error", 0)
    checks.append(Check(
        "model_review.bpa_errors", "model_review", FAIL if errors > c["max_errors"] else PASS,
        "Reglas BPA de severidad Error",
        f"{errors} violaciones (máximo {c['max_errors']}).",
        {"count": errors, "rules": sorted({f['rule'] for f in findings if f['severity'] == 'Error'})},
    ))
    warnings = counts.get("Warning", 0)
    checks.append(Check(
        "model_review.bpa_warnings", "model_review", WARN if warnings > c["max_warnings"] else PASS,
        "Reglas BPA de severidad Warning",
        f"{warnings} violaciones (máximo recomendado {c['max_warnings']}).",
        {"count": warnings},
    ))
    blocking = {r.lower() for r in c.get("blocking_rules", [])}
    hit = sorted({f["rule"] for f in findings if f["rule"].lower() in blocking})
    if blocking:
        checks.append(Check(
            "model_review.blocking_rules", "model_review", FAIL if hit else PASS,
            "Reglas bloqueantes del equipo", ", ".join(hit) if hit else "Ninguna regla bloqueante violada.",
            {"rules": hit},
        ))

    vp = review.get("vertipaq") or {}
    size_mb = vp.get("model_size_mb")
    sku = str(c.get("sku") or "").upper()
    if size_mb is None:
        checks.append(Check("model_review.memory", "model_review", SKIP, "Tamaño del modelo en memoria",
                            "Sin estadísticas VertiPaq."))
    elif sku in SKU_MAX_MODEL_MEMORY_GB:
        limit_mb = SKU_MAX_MODEL_MEMORY_GB[sku] * 1024
        pct = 100.0 * size_mb / limit_mb
        checks.append(Check(
            "model_review.memory", "model_review", WARN if pct > c["max_model_memory_pct_of_sku"] else PASS,
            f"Memoria del modelo frente al límite de {sku}",
            f"{n(size_mb, 0)} MB = {n(pct, 0)} % del máximo por modelo ({SKU_MAX_MODEL_MEMORY_GB[sku]} GB). "
            "El refresco completo puede necesitar el doble.",
            {"model_size_mb": size_mb, "pct_of_sku_limit": round(pct, 1), "sku": sku},
        ))
    small = size_mb is not None and size_mb < c.get("min_model_mb_for_column_check", 100)
    heavy = [] if small else [col for col in vp.get("top_columns", [])
                              if (col.get("pct_of_model") or 0) > c["max_column_pct_of_model"]]
    if size_mb is not None:
        checks.append(Check(
            "model_review.heavy_columns", "model_review", WARN if heavy else PASS,
            "Columnas que dominan el tamaño del modelo",
            ", ".join(f"{h['table']}[{h['column']}] {n(h['pct_of_model'])} %" for h in heavy)
            or (f"Modelo de {n(size_mb, 1)} MB: por debajo de {c.get('min_model_mb_for_column_check', 100)} MB no se evalúa." if small
                else "Ninguna por encima del umbral."),
            {"columns": heavy},
        ))
    return checks
