"""Recomendaciones accionables a partir de las tres evidencias. Reglas simples y explicables: cada consejo cita su dato."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .checks import Advice, n
from .loadtest import evaluation_level, sustained_level

# Acciones concretas para las reglas de BPA más frecuentes (nombres de las reglas de semantic-link-labs).
_BPA_ACTIONS = [
    ("floating point", "Cambia las columnas Double a Decimal fijo (Currency) o entero: comprimen mejor y evitan errores de redondeo."),
    ("bi-directional", "Elimina relaciones bidireccionales; usa CROSSFILTER solo dentro de las medidas que lo necesiten."),
    ("many-to-many", "Sustituye la relación muchos a muchos por una tabla puente con relaciones 1:N."),
    ("auto-date", "Desactiva Auto date/time y usa una tabla de fechas marcada como tal."),
    ("isavailableinmdx", "Pon IsAvailableInMDX = false en columnas que no se usan como atributo: reduce memoria y procesado."),
    ("partition", "Particiona las tablas grandes y usa refresco incremental."),
    ("date and time", "Separa fecha y hora en dos columnas: baja la cardinalidad de forma drástica."),
    ("calculated column", "Mueve las columnas calculadas a Power Query o a la vista de origen."),
    ("divide", "Usa DIVIDE() en vez del operador / para las divisiones con posible denominador cero."),
    ("iferror", "Evita IFERROR/ISERROR: fuerzan evaluación celda a celda; controla el error en origen."),
    ("row level security", "Simplifica las expresiones RLS: filtros sobre dimensiones pequeñas, sin LOOKUPVALUE ni iteradores."),
    ("snowflake", "Desnormaliza el copo de nieve a esquema en estrella."),
    ("unused", "Quita del modelo las columnas y tablas que ningún informe ni medida usa."),
    ("relationship", "Revisa la columna clave de la relación: entera, sin nulos y de baja cardinalidad."),
]


def _bpa_advice(review: dict[str, Any] | None, cfg: dict[str, Any]) -> list[Advice]:
    if not review or not review.get("findings"):
        return []
    ignored = {r.lower() for r in cfg["model_review"].get("ignored_rules", [])}
    grouped: dict[str, dict[str, Any]] = {}
    for f in review["findings"]:
        if f["rule"].lower() in ignored:
            continue
        g = grouped.setdefault(f["rule"], {**f, "objects": []})
        g["objects"].append(f["object_name"])
    out = []
    for rule, g in grouped.items():
        sev, cat = g["severity"], g["category"].lower()
        priority = 1 if sev == "Error" or (sev == "Warning" and "perf" in cat) else 2 if sev == "Warning" else 3
        action = next((a for k, a in _BPA_ACTIONS if k in rule.lower()), g["description"] or "Revisa la regla y corrige los objetos afectados.")
        objs = g["objects"]
        out.append(Advice("model_review", priority, f"BPA: {rule}", action,
                          f"{len(objs)} objeto(s): {', '.join(objs[:5])}{' …' if len(objs) > 5 else ''} ({sev}, {g['category']})",
                          g["url"]))
    return sorted(out, key=lambda a: (a.priority, -int(a.evidence.split(" ")[0])))[:15]


def _vertipaq_advice(review: dict[str, Any] | None, cfg: dict[str, Any]) -> list[Advice]:
    vp = (review or {}).get("vertipaq") or {}
    out = []
    if (vp.get("model_size_mb") or 0) < cfg["model_review"].get("min_model_mb_for_column_check", 100):
        return out
    for col in vp.get("top_columns", [])[:5]:
        if (col.get("pct_of_model") or 0) >= cfg["model_review"]["max_column_pct_of_model"]:
            out.append(Advice(
                "model_review", 1, f"Columna pesada {col['table']}[{col['column']}]",
                "Quítala si no se usa; si es clave de texto o GUID, sustitúyela por un entero; si es fecha y hora, sepárala; "
                "reduce decimales.", f"{n(col['size_mb'], 0)} MB, {n(col['pct_of_model'], 1)} % del modelo, cardinalidad {col.get('cardinality')}"))
    return out


def _load_advice(summary: dict[str, Any] | None, capacity: dict[str, Any] | None, cfg: dict[str, Any]) -> list[Advice]:
    if not summary:
        return []
    c = cfg["load_test"]
    out = []
    for m in summary.get("models", []):
        key = m["model_key"]
        for v in m.get("slow_visuals", []):
            if not v["slow"]:
                continue
            if v.get("growth") is not None and v["growth"] >= 3:
                out.append(Advice(
                    "load_test", 1, f"{key}: «{v['visual']}» se degrada con la concurrencia",
                    "Contención: la consulta pasa mucho tiempo en el formula engine (un hilo por consulta). Reduce iteradores "
                    "sobre tablas grandes, materializa en el origen o usa agregaciones; mira Server Timings en DAX Studio.",
                    f"p95 {n(v['p95_first_level'], 2)} s → {n(v['p95'], 2)} s (×{n(v['growth'], 1)}) con {v['level']} usuarios"))
            else:
                out.append(Advice(
                    "load_test", 1, f"{key}: «{v['visual']}» es lenta incluso sin carga",
                    "El problema es la consulta, no la concurrencia: optimiza la medida (Server Timings, SE frente a FE, "
                    "CallbackDataID), reduce los campos del visual o divide el visual.",
                    f"p95 {n(v['p95'], 2)} s con {v['level']} usuarios; {n(v.get('p95_first_level'), 2)} s con el primer nivel"))
        ev = evaluation_level(m["levels"], c["target_level"])
        sus = sustained_level(m["levels"], c)
        if ev and sus < c["target_level"]:
            out.append(Advice(
                "load_test", 1, f"{key}: sostiene {sus} usuarios de {c['target_level']}",
                "Optimiza las consultas de la lista y repite la rampa; si ya están optimizadas, dimensiona el SKU con "
                "la utilización medida en Capacity Metrics.", f"p95 {n(ev['p95'], 2)} s con {ev['level']} usuarios"))
        errs = [s for lv in m["levels"] for s in lv["error_samples"]]
        if any(lv["failed_queries"] for lv in m["levels"]):
            hint = "Timeouts o rechazos por throttling" if any("throttl" in e.lower() or "timeout" in e.lower() for e in errs) \
                else "Revisa error.log del nivel"
            out.append(Advice("load_test", 1, f"{key}: consultas fallidas en la rampa",
                              f"{hint}. Corrige antes de comparar latencias; con el orquestador anterior a 3.4.0 un usuario que falla pierde todas sus filas.",
                              "; ".join(errs[:2]) or "usuarios virtuales sin CSV"))
        if capacity and ev and ev["p95"] > c["p95_sec"] and capacity.get("peak_utilization_pct", 100) < 50 \
                and capacity.get("peak_interactive_delay_pct", 100) < 50:
            out.append(Advice(
                "load_test", 2, f"{key}: latencia alta con la capacidad holgada",
                "Puede ser el generador de carga: sube vCores en %%configure de RunLoadTest_v3 o reparte usuarios; "
                "si persiste, es contención dentro del modelo (consultas FE-bound).",
                f"p95 {n(ev['p95'], 2)} s con utilización pico {n(capacity['peak_utilization_pct'], 1)} %"))
    return out


def _capacity_advice(capacity: dict[str, Any] | None, cfg: dict[str, Any]) -> list[Advice]:
    if not capacity or capacity.get("error") or not capacity.get("timepoints_in_window"):
        return []
    c = cfg["capacity"]
    out = []
    if capacity["peak_utilization_pct"] > c["max_utilization_pct"]:
        out.append(Advice("capacity", 1, "Capacidad al límite durante el test",
                          "Optimiza las operaciones con más CU del modelo; si es carga legítima, escala el SKU o activa "
                          "surge protection para proteger los informes interactivos.",
                          f"pico {n(capacity['peak_utilization_pct'], 1)} %",
                          "https://learn.microsoft.com/fabric/enterprise/surge-protection"))
    if capacity["peak_interactive_delay_pct"] >= c["warn_interactive_delay_pct"]:
        out.append(Advice("capacity", 1, "Throttling interactivo cerca o activo",
                          "El smoothing de 10 minutos ya no absorbe la carga: reduce CU por consulta o reparte el pico.",
                          f"retraso interactivo {n(capacity['peak_interactive_delay_pct'], 1)} % del umbral",
                          "https://learn.microsoft.com/fabric/enterprise/throttling"))
    tool = capacity.get("tooling") or {}
    if tool.get("workspace_id") and tool.get("share_pct", 0) > c["max_tooling_cu_share_pct"]:
        out.append(Advice("capacity", 2, "El generador de carga consume en la misma capacidad",
                          "Mueve el workspace del orquestador a otra capacidad para que Spark no contamine la medida.",
                          f"{n(tool['share_pct'], 1)} % del CU del día"))
    ops = (capacity.get("model") or {}).get("operations") or []
    if ops:
        top = ops[0]
        out.append(Advice("capacity", 3, f"Operación con más CU del modelo: {top['operation']}",
                          "Úsala como línea base de CU para comparar la próxima versión del modelo.",
                          f"{n(top['cu_s'], 0)} CU(s) en {top['operations']} operaciones ({n(top['cu_s_per_operation'], 2)} CU(s) por operación)"))
    return out


def build_advice(review, summary, capacity, cfg) -> list[Advice]:
    advice = _bpa_advice(review, cfg) + _vertipaq_advice(review, cfg) + _load_advice(summary, capacity, cfg) \
        + _capacity_advice(capacity, cfg)
    seen, out = set(), []
    for a in sorted(advice, key=lambda a: a.priority):
        if a.title not in seen:
            seen.add(a.title)
            out.append(a)
    return out


def group_by_area(advice: list[Advice]) -> dict[str, list[Advice]]:
    g: dict[str, list[Advice]] = defaultdict(list)
    for a in advice:
        g[a.area].append(a)
    return g
