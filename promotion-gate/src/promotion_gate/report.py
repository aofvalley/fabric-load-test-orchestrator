"""Informe del gate en Markdown: lo lee el equipo en el PR, en el lakehouse o en el chat del plugin."""

from __future__ import annotations

from typing import Any

from .checks import n

_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "SKIP": "⏭️"}
_AREA = {"model_review": "Revisión del modelo", "load_test": "Test de carga", "capacity": "Capacity Metrics"}
_PRIO = {1: "Alta", 2: "Media", 3: "Baja"}


def _cell(v: Any) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return n(v, 2)
    return str(v).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_cell(x) for x in r) + " |" for r in rows]
    return out


def render_markdown(verdict: dict[str, Any], review: dict[str, Any] | None = None,
                    load_summary: dict[str, Any] | None = None, capacity: dict[str, Any] | None = None) -> str:
    ctx = verdict.get("context", {})
    v = verdict["verdict"]
    lines = [
        f"# Gate de promoción: {ctx.get('dataset', 'modelo semántico')}",
        "",
        f"**Veredicto: {_ICON[v]} {v}**. "
        + ("Listo para promocionar." if verdict["promotable"] else "No se puede promocionar todavía."),
        "",
        f"Run `{ctx.get('run_id', '-')}`, evaluado {verdict['evaluated_utc']}, gate {verdict['gate_version']}.",
        "",
        "## Resumen por área",
        "",
    ]
    lines += _table(["Área", "Estado"], [[_AREA[a], f"{_ICON[s]} {s}"] for a, s in verdict["areas"].items()])
    lines += ["", "## Comprobaciones", ""]
    lines += _table(["", "Área", "Comprobación", "Detalle"],
                    [[_ICON[c["status"]], _AREA[c["area"]], c["title"], c["detail"]] for c in verdict["checks"]])

    advice = verdict.get("advice", [])
    lines += ["", "## Mejoras recomendadas", ""]
    if advice:
        lines += _table(["Prioridad", "Área", "Qué", "Acción", "Dato"],
                        [[_PRIO[a["priority"]], _AREA[a["area"]], a["title"],
                          a["action"] + (f" ([doc]({a['reference']}))" if a.get("reference") else ""), a["evidence"]]
                         for a in advice])
    else:
        lines.append("Sin recomendaciones: ninguna regla ha saltado.")

    if load_summary and load_summary.get("models"):
        lines += ["", "## Test de carga", ""]
        w = load_summary.get("window", {})
        lines.append(f"Ventana UTC: {w.get('start_utc')} → {w.get('end_utc')}.")
        for m in load_summary["models"]:
            lines += ["", f"### {m['model']} (`{m['model_key']}`)", ""]
            lines += _table(["Usuarios", "Consultas", "Fallidas", "p50 s", "p90 s", "p95 s", "máx s", "QPS", "Duración s"],
                            [[lv["level"], lv["queries"], lv["failed_queries"], lv["p50"], lv["p90"], lv["p95"], lv["max"],
                              lv["qps"], lv["duration_s"]] for lv in m["levels"]])
            if m.get("slow_visuals"):
                lines += ["", "Visuales con más latencia en el último nivel:", ""]
                lines += _table(["Visual", "p95 s", "p95 primer nivel s", "Crecimiento", "Lenta"],
                                [[s["visual"], s["p95"], s["p95_first_level"], s["growth"], "sí" if s["slow"] else "no"]
                                 for s in m["slow_visuals"]])
            if m.get("slow_queries"):
                lines += ["", "<details><summary>Consultas DAX más lentas</summary>", ""]
                for q in m["slow_queries"]:
                    lines += [f"- **{q['visual']}** (consulta {q['query_number']}): p95 {n(q['p95'], 2)} s, {q['rows']} filas", "",
                              "  ```dax", f"  {q['dax']}", "  ```", ""]
                lines.append("</details>")

    if capacity and not capacity.get("error"):
        lines += ["", "## Capacity Metrics", ""]
        lines += _table(["Métrica", "Valor"], [
            ["Versión del modelo de la app", capacity.get("version")],
            ["Timepoints en la ventana", capacity.get("timepoints_in_window")],
            ["Hora de los timepoints de la app", f"UTC{capacity.get('utc_offset_hours') or 0:+g} (convertidos a UTC)"],
            ["Utilización pico / media %", f"{capacity.get('peak_utilization_pct')} / {capacity.get('avg_utilization_pct')}"],
            ["Retraso interactivo pico % umbral", capacity.get("peak_interactive_delay_pct")],
            ["Rechazo interactivo pico % umbral", capacity.get("peak_interactive_rejection_pct")],
            ["Carry-over pico %", capacity.get("peak_carryover_pct")],
            ["CU(s) del modelo en el día", (capacity.get("model") or {}).get("cu_s")],
            ["CU del generador de carga % del día", (capacity.get("tooling") or {}).get("share_pct")],
        ])
        ops = (capacity.get("model") or {}).get("operations") or []
        if ops:
            lines += ["", "Operaciones del modelo (día completo):", ""]
            lines += _table(["Operación", "CU(s)", "Operaciones", "CU(s)/op", "Fallidas", "Rechazadas", "Throttling min"],
                            [[o["operation"], o["cu_s"], o["operations"], o["cu_s_per_operation"], o["failed"], o["rejected"],
                              o["throttling_min"]] for o in ops])

    if review and review.get("vertipaq"):
        vp = review["vertipaq"]
        lines += ["", "## Revisión del modelo", "", f"Tamaño en memoria: {n(vp.get('model_size_mb'), 1)} MB."]
        if vp.get("top_columns"):
            lines += [""] + _table(["Tabla", "Columna", "MB", "% modelo", "Cardinalidad"],
                                   [[c["table"], c["column"], c["size_mb"], c["pct_of_model"], c["cardinality"]]
                                    for c in vp["top_columns"]])

    lines += ["", "## Límites de la evidencia", "",
              "- La latencia es la del cliente (notebook): incluye red y cola, no solo el motor.",
              "- Los usuarios repiten las mismas consultas: la caché del motor hace que el resultado sea optimista.",
              "- La tabla diaria de Capacity Metrics suma todo el día; los timepoints sí son de la ventana exacta.", ""]
    return "\n".join(lines)
