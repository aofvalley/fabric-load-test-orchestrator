"""Lectura del modelo semántico de la app Fabric Capacity Metrics para la ventana del test.

Las consultas DAX son las mismas que usa FUAM (microsoft/fabric-toolbox, monitoring/fabric-unified-admin-monitoring),
que detecta la versión del modelo de la app con sondas y adapta los nombres. Se soportan v40, v44, v47 y v53;
v37 y anteriores usan otros nombres de tabla y no se soportan (actualiza la app).

Granularidad:
- TimePoints: 30 s. Da utilización, throttling (retraso y rechazo) y carry-over de la capacidad en la ventana exacta.
- Metrics By Item Operation And Day: día. Da CU, operaciones fallidas, rechazadas y minutos de throttling del modelo
  y del propio generador de carga. Al ser diaria incluye el resto de actividad del día sobre esos items.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .checks import FAIL, PASS, SKIP, WARN, Check, n

SUPPORTED_VERSIONS = ("v53", "v47", "v44", "v40")

# Orden y DAX de las sondas de FUAM: la primera que responde fija la versión.
VERSION_PROBES: list[tuple[str, str]] = [
    ("v53", """EVALUATE ROW("Blocked_workspaces__Day_", 'All Measures'[Blocked workspaces (Day)])"""),
    ("v47", """DEFINE MPARAMETER 'DefaultCapacityID' = "0000000-0000-0000-0000-00000000"
EVALUATE SUMMARIZECOLUMNS("Background billable CU %", [Background billable CU %])"""),
    ("v40", """EVALUATE ROW("Background billable CU %", 'All Measures'[Background billable CU %])"""),
    ("v37", """EVALUATE ROW("xBackground__", 'All Measures'[xBackground %])"""),
]

_TP_MEASURES = """
        "B_P", 'All Measures'[Background billable CU %],
        "I_P", 'All Measures'[Interactive billable CU %],
        "B_NB_P", 'All Measures'[Background non billable CU %],
        "I_NB_P", 'All Measures'[Interactive non billable CU %],
        "AS_P", 'All Measures'[SKU CU by timepoint %],
        "CU_L", 'All Measures'[CU limit],
        "I_Del_P", 'All Measures'[Dynamic interactive delay %],
        "I_Rej_P", 'All Measures'[Dynamic interactive rejection %],
        "B_Rej_P", 'All Measures'[Dynamic background rejection %],
        "CO_C_P", 'All Measures'[Cumulative carry over %],
        "Exp_BD_M", 'All Measures'[Expected burndown in minutes]"""

_IO_MEASURES = """
        "S_Dur", SUM('Metrics By Item Operation And Day'[Duration (s)]),
        "S_CU", SUM('Metrics By Item Operation And Day'[CU (s)]),
        "TH_M", SUM('Metrics By Item Operation And Day'[Throttling (min)]),
        "C_U", SUM('Metrics By Item Operation And Day'[Users]),
        "C_SO", SUM('Metrics By Item Operation And Day'[Successful operations]),
        "C_RO", SUM('Metrics By Item Operation And Day'[Rejected operations]),
        "C_O", SUM('Metrics By Item Operation And Day'[Operations]),
        "C_FO", SUM('Metrics By Item Operation And Day'[Failed operations]),
        "C_CO", SUM('Metrics By Item Operation And Day'[Cancelled operations])"""


def _check_guid(value: str) -> str:
    text = str(value).strip()
    if not text or any(ch not in "0123456789abcdefABCDEF-" for ch in text):
        raise ValueError(f"capacity_id no es un GUID válido: {value!r}")
    return text


def _mparam(version: str, capacity_id: str) -> str:
    if version == "v40":
        return f"MPARAMETER 'CapacityID' = \"{capacity_id}\""
    return f"MPARAMETER 'CapacitiesList' = {{ \"{capacity_id}\" }}"


def timepoints_query(version: str, capacity_id: str, day: date) -> str:
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"Versión de Capacity Metrics no soportada: {version}")
    cap = _check_guid(capacity_id)
    if version == "v53":
        filters = (f"TREATAS({{\"{cap}\"}}, 'Capacities'[Capacity Id]),\n"
                   f"        TREATAS({{DATE({day.year}, {day.month}, {day.day})}}, 'Dates'[Date]),")
    else:
        filters = (f"FILTER(Capacities, Capacities[capacity Id] = \"{cap}\"),\n"
                   f"        FILTER(TimePoints, 'TimePoints'[Date] = DATE({day.year}, {day.month}, {day.day})),")
    return f"""DEFINE
    {_mparam(version, cap)}
VAR __DS0Core =
    SUMMARIZECOLUMNS(
        'TimePoints'[TimePoint],
        {filters}{_TP_MEASURES}
    )
EVALUATE __DS0Core"""


def item_operation_query(version: str, capacity_id: str, day: date) -> str:
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"Versión de Capacity Metrics no soportada: {version}")
    cap = _check_guid(capacity_id)
    cap_col = "Capacities[Capacity Id]" if version == "v53" else "Capacities[capacity Id]"
    return f"""DEFINE
    {_mparam(version, cap)}
VAR __DS0FilterTable =
    FILTER(
        KEEPFILTERS(VALUES('Metrics By Item Operation And Day'[Date])),
        'Metrics By Item Operation And Day'[Date] = DATE({day.year}, {day.month}, {day.day})
    )
VAR __DS0Core =
    SUMMARIZECOLUMNS(
        Items[Workspace Id],
        'Metrics By Item Operation And Day'[Item Id],
        'Items'[Item Kind],
        'Metrics By Item Operation And Day'[Operation name],
        FILTER(Capacities, {cap_col} = "{cap}"),
        __DS0FilterTable,{_IO_MEASURES}
    )
EVALUATE FILTER(__DS0Core, [S_CU] > 0)"""


def item_operation_hour_query(version: str, capacity_id: str, start_local: datetime, end_local: datetime) -> str:
    """Operaciones por item en las horas del test (v53, tabla horaria, hora local de la app). Más preciso que el día."""
    if version != "v53":
        raise ValueError("La tabla horaria por item solo se usa con Capacity Metrics v53")
    cap = _check_guid(capacity_id)
    t = "'Metrics By Item Operation And Hour'"
    lo, hi = start_local.replace(minute=0, second=0, microsecond=0), end_local.replace(minute=0, second=0, microsecond=0)
    at = lambda d: f"DATE({d.year}, {d.month}, {d.day}) + TIME({d.hour}, 0, 0)"
    sums = ",\n        ".join(f'"{k}", SUM({t}[{c}])' for k, c in (
        ("S_Dur", "Duration (s)"), ("S_CU", "CU (s)"), ("TH_M", "Throttling (min)"), ("C_RO", "Rejected operations"),
        ("C_O", "Operations"), ("C_FO", "Failed operations")))
    return f"""DEFINE
    {_mparam(version, cap)}
VAR __Hours = FILTER(ALL({t}[Datetime]), {t}[Datetime] >= {at(lo)} && {t}[Datetime] <= {at(hi)})
VAR __DS0Core =
    SUMMARIZECOLUMNS(
        {t}[Workspace Id],
        {t}[Item Id],
        {t}[Operation name],
        __Hours,
        FILTER(Capacities, Capacities[Capacity Id] = "{cap}"),
        {sums}
    )
EVALUATE FILTER(__DS0Core, [S_CU] > 0)"""


def detect_version(evaluate: Callable[[str], Any]) -> str:
    """`evaluate(dax)` lanza excepción si la consulta no es válida para el modelo."""
    for version, probe in VERSION_PROBES:
        try:
            evaluate(probe)
            return version
        except Exception:  # noqa: BLE001 - la sonda falla a propósito en versiones distintas
            continue
    raise RuntimeError("No se reconoce el modelo de Capacity Metrics o no hay acceso a él.")


def norm_key(col: str) -> str:
    """'Capacities[capacity Id]' -> 'capacity Id'; '[B_P]' -> 'B_P'."""
    text = str(col)
    if text.endswith("]") and "[" in text:
        return text[text.rfind("[") + 1:-1]
    return text


_CANONICAL_KEYS = {k.lower(): k for k in ("TimePoint", "Item Id", "Workspace Id", "Item Kind", "Operation name")}


def normalize_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las versiones de la app cambian mayúsculas (v53 devuelve 'Timepoints[Timepoint]' e 'Items[Item kind]')."""
    def key(col: str) -> str:
        name = norm_key(col)
        return _CANONICAL_KEYS.get(name.lower(), name)
    return [{key(k): v for k, v in r.items()} for r in records or []]


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


to_dt = _to_dt

# La app guarda los timepoints en la hora local de su parámetro UTC_offset (el de la instalación) y expone ese desfase
# en 'Latest Summary Timestamp'[UTC Offset]. La ventana del test va en UTC: sin convertir se mira otra hora del día.
UTC_OFFSET_QUERY = "EVALUATE 'Latest Summary Timestamp'"


def parse_utc_offset(rows: list[dict[str, Any]] | None) -> float:
    """Horas de desfase de los timepoints respecto a UTC; 0 si la versión de la app no lo expone."""
    for r in normalize_rows(rows or []):
        for k, v in r.items():
            if k.replace(" ", "").lower() == "utcoffset" and v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def timepoint_utc(value: Any, utc_offset_hours: float = 0.0) -> datetime | None:
    dt = _to_dt(value)
    return dt - timedelta(hours=utc_offset_hours) if dt else None


def days_in_window(start_utc: str, end_utc: str, utc_offset_hours: float = 0.0) -> list[date]:
    """Días (en la hora local de la app) que cubre la ventana UTC del test."""
    s, e = _to_dt(start_utc), _to_dt(end_utc)
    if not s or not e:
        return []
    s, e = s + timedelta(hours=utc_offset_hours), e + timedelta(hours=utc_offset_hours)
    out, d = [], s.date()
    while d <= e.date():
        out.append(d)
        d += timedelta(days=1)
    return out


def _f(v: Any) -> float:
    try:
        x = float(v)
        return 0.0 if x != x else x
    except (TypeError, ValueError):
        return 0.0


def percent_scale(timepoints: list[dict[str, Any]]) -> float:
    """El modelo devuelve fracciones (1.0 = 100 %) o porcentajes. 'SKU CU by timepoint %' es la línea del SKU
    (100 %), así que su mediana distingue un caso del otro."""
    refs = sorted(_f(r.get("AS_P")) for r in timepoints if _f(r.get("AS_P")) > 0)
    if not refs:
        return 100.0
    median = refs[len(refs) // 2]
    return 100.0 if median <= 5 else 1.0


def analyze(timepoints: list[dict[str, Any]], item_operations: list[dict[str, Any]], window: dict[str, str],
            model_item_id: str, tooling_workspace_id: str | None = None, margin_min: int = 5,
            version: str | None = None, capacity_id: str | None = None, utc_offset_hours: float = 0.0,
            operations_scope: str = "day") -> dict[str, Any]:
    tps = normalize_rows(timepoints)
    ios = normalize_rows(item_operations)
    s, e = _to_dt(window.get("start_utc")), _to_dt(window.get("end_utc"))
    if s and e:
        s, e = s - timedelta(minutes=margin_min), e + timedelta(minutes=margin_min)
    scale = percent_scale(tps)
    in_win = [r for r in tps if (dt := timepoint_utc(r.get("TimePoint"), utc_offset_hours)) and (not s or s <= dt <= e)]
    latest = max((dt for r in tps if (dt := timepoint_utc(r.get("TimePoint"), utc_offset_hours))), default=None)
    test_end = _to_dt(window.get("end_utc"))
    util = [(_f(r.get("B_P")) + _f(r.get("I_P"))) * scale for r in in_win]

    def peak(key: str) -> float:
        return round(max((_f(r.get(key)) * scale for r in in_win), default=0.0), 1)

    model_id = str(model_item_id or "").lower()
    model_ops = [r for r in ios if str(r.get("Item Id", "")).lower() == model_id]
    tooling_ops = [r for r in ios if tooling_workspace_id
                   and str(r.get("Workspace Id", "")).lower() == str(tooling_workspace_id).lower()
                   and str(r.get("Item Id", "")).lower() != model_id]
    total_cu = sum(_f(r.get("S_CU")) for r in ios)
    tooling_cu = sum(_f(r.get("S_CU")) for r in tooling_ops)
    by_op = {}
    for r in model_ops:
        op = by_op.setdefault(r.get("Operation name") or "?", {"operation": r.get("Operation name") or "?",
                                                                 "cu_s": 0.0, "duration_s": 0.0, "operations": 0,
                                                                 "failed": 0, "rejected": 0, "throttling_min": 0.0})
        op["cu_s"] += _f(r.get("S_CU"))
        op["duration_s"] += _f(r.get("S_Dur"))
        op["operations"] += int(_f(r.get("C_O")))
        op["failed"] += int(_f(r.get("C_FO")))
        op["rejected"] += int(_f(r.get("C_RO")))
        op["throttling_min"] += _f(r.get("TH_M"))
    ops = sorted(by_op.values(), key=lambda o: o["cu_s"], reverse=True)
    for o in ops:
        o["cu_s"], o["duration_s"], o["throttling_min"] = round(o["cu_s"], 1), round(o["duration_s"], 1), round(o["throttling_min"], 2)
        o["cu_s_per_operation"] = round(o["cu_s"] / o["operations"], 3) if o["operations"] else None
    return {
        "version": version, "capacity_id": capacity_id, "window": window, "utc_offset_hours": utc_offset_hours,
        "operations_scope": operations_scope,
        "timepoints_in_window": len(in_win),
        "percent_scale": scale,
        "latest_timepoint_utc": latest.isoformat() if latest else None,
        "covers_window_end": bool(latest and test_end and latest >= test_end),
        "peak_utilization_pct": round(max(util, default=0.0), 1),
        "avg_utilization_pct": round(sum(util) / len(util), 1) if util else 0.0,
        "peak_interactive_delay_pct": peak("I_Del_P"),
        "peak_interactive_rejection_pct": peak("I_Rej_P"),
        "peak_background_rejection_pct": peak("B_Rej_P"),
        "peak_carryover_pct": peak("CO_C_P"),
        "model": {
            "item_id": model_item_id, "found": bool(model_ops), "operations": ops,
            "cu_s": round(sum(o["cu_s"] for o in ops), 1),
            "failed_operations": sum(o["failed"] for o in ops),
            "rejected_operations": sum(o["rejected"] for o in ops),
            "throttling_min": round(sum(o["throttling_min"] for o in ops), 2),
        },
        "tooling": {"workspace_id": tooling_workspace_id, "cu_s": round(tooling_cu, 1), "found": bool(tooling_ops),
                    "share_pct": round(100.0 * tooling_cu / total_cu, 1) if total_cu else 0.0},
        "capacity_cu_s_day": round(total_cu, 1),
    }


def _scope(metrics: dict[str, Any]) -> str:
    return "horas del test" if metrics.get("operations_scope") == "hour" else "día completo"


def evaluate_capacity(metrics: dict[str, Any] | None, cfg: dict[str, Any]) -> list[Check]:
    c = cfg["capacity"]
    if not metrics or metrics.get("error"):
        status = FAIL if c["required"] else SKIP
        detail = (metrics or {}).get("error") or "No existe capacity.json: el notebook NB_Gate_CapacityMetrics no terminó."
        return [Check("capacity.evidence", "capacity", status, "Sin evidencia de Capacity Metrics", str(detail))]
    if not metrics.get("timepoints_in_window"):
        return [Check("capacity.evidence", "capacity", FAIL if c["required"] else SKIP,
                      "Capacity Metrics sin datos en la ventana del test",
                      "La app tarda entre 10 y 15 minutos en reflejar el consumo; sube metrics_lag_minutes (espera máxima) y repite "
                      "solo NB_Gate_CapacityMetrics y NB_Gate_Verdict.")]
    if not metrics.get("covers_window_end", True):
        return [Check("capacity.evidence", "capacity", FAIL if c["required"] else SKIP,
                      "Capacity Metrics incompleto: no cubre el final del test",
                      f"Último timepoint {metrics.get('latest_timepoint_utc')}, el test terminó a las "
                      f"{(metrics.get('window') or {}).get('end_utc')}. Falta el nivel más alto de la rampa; repite "
                      "NB_Gate_CapacityMetrics y NB_Gate_Verdict más tarde.")]
    checks = [
        Check("capacity.utilization", "capacity",
              FAIL if metrics["peak_utilization_pct"] > c["max_utilization_pct"] else PASS,
              "Pico de utilización de la capacidad",
              f"{n(metrics['peak_utilization_pct'], 1)} % (máximo {n(c['max_utilization_pct'])} %); media {n(metrics['avg_utilization_pct'], 1)} %.",
              {"peak": metrics["peak_utilization_pct"], "avg": metrics["avg_utilization_pct"]}),
    ]
    delay = metrics["peak_interactive_delay_pct"]
    checks.append(Check(
        "capacity.interactive_delay", "capacity",
        FAIL if delay >= c["max_interactive_delay_pct"] else WARN if delay >= c["warn_interactive_delay_pct"] else PASS,
        "Throttling interactivo (retraso)",
        f"Pico {n(delay, 1)} % del umbral de retraso (100 % = las consultas interactivas se retrasan).", {"peak": delay}))
    rej = metrics["peak_interactive_rejection_pct"]
    checks.append(Check(
        "capacity.interactive_rejection", "capacity",
        FAIL if rej >= 100 else WARN if rej >= c["warn_interactive_rejection_pct"] else PASS,
        "Throttling interactivo (rechazo)", f"Pico {n(rej, 1)} % del umbral de rechazo (100 % = se rechazan consultas).", {"peak": rej}))
    model = metrics["model"]
    tooling = metrics.get("tooling") or {}
    if not model["found"] and tooling.get("workspace_id") and not tooling.get("found"):
        # Ni el modelo ni los notebooks del generador: la tabla diaria (se refresca con la app) aún no cubre el test.
        checks.append(Check("capacity.model_found", "capacity", SKIP, "Operaciones del modelo pendientes en Capacity Metrics",
                            f"La tabla por item ({_scope(metrics)}) todavía no incluye el test (tampoco los notebooks del generador). "
                            "La utilización y el throttling de la ventana sí están medidos; repite NB_Gate_CapacityMetrics "
                            "tras el siguiente refresco de la app para ver CU y operaciones del modelo."))
    elif not model["found"]:
        checks.append(Check("capacity.model_found", "capacity", WARN, "Modelo no encontrado en Capacity Metrics",
                            "El item no aparece en la tabla diaria; comprueba el item id y que el modelo esté en la capacidad indicada."))
    else:
        bad = model["failed_operations"] + model["rejected_operations"]
        checks.append(Check(
            "capacity.model_operations", "capacity", FAIL if bad > c["max_model_failed_operations"] else PASS,
            "Operaciones fallidas o rechazadas del modelo",
            f"{model['failed_operations']} fallidas, {model['rejected_operations']} rechazadas, "
            f"{n(model['throttling_min'], 1)} min de throttling ({_scope(metrics)}).", {"failed": model["failed_operations"],
                                                                              "rejected": model["rejected_operations"]}))
    tool = metrics["tooling"]
    if tool.get("workspace_id"):
        checks.append(Check(
            "capacity.tooling_share", "capacity", WARN if tool["share_pct"] > c["max_tooling_cu_share_pct"] else PASS,
            "Consumo del propio generador de carga",
            f"Los notebooks del test suponen el {n(tool['share_pct'], 1)} % del CU de la capacidad ({_scope(metrics)}). "
            "Si comparten capacidad con el modelo, contaminan la medida.", {"share_pct": tool["share_pct"]}))
    return checks
