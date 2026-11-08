"""Análisis del test de carga a partir de los CSV que escribe el Fabric Load Test Orchestrator.

Estructura de entrada (la del orquestador v3):
    Files/PerfScenarios/logs/<prefijo>-<model_key>-c<N>-<yyyymmdd-hhmmss>/<loadtestId>_user_<k>.csv
    .../error.log                (solo si algún usuario virtual falló)
    .../thinktimes/*.csv         (se ignora aquí)

Desde la versión 3.4.0 del orquestador cada consulta fallida es una fila con status = error y su mensaje, y el CSV se
escribe siempre. Un usuario que no llega a conectar sigue sin CSV, así que el error se mide como consultas fallidas más
las que faltan frente a las esperadas (usuarios × consultas por usuario). Los CSV anteriores, sin status, se leen como
consultas correctas. Los percentiles solo usan consultas correctas.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import FAIL, PASS, WARN, Check, n, pc, percentile

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
RUN_DIR = re.compile(r"^(?P<name>.+)-c(?P<level>\d+)-(?P<ts>\d{8}-\d{6})$")


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def read_runs(logs_dir: str | Path, run_prefix: str, since_epoch: float | None = None) -> list[dict[str, Any]]:
    """Lee las carpetas `<run_prefix>-*` y devuelve una entrada por (modelo, nivel) con sus filas."""
    root = Path(logs_dir)
    runs = []
    for folder in sorted(root.glob(f"{run_prefix}-*")):
        m = RUN_DIR.match(folder.name)
        if not folder.is_dir() or not m:
            continue
        model_key = m.group("name")[len(run_prefix) + 1:] or m.group("name")
        rows: list[dict[str, Any]] = []
        for f in sorted(folder.glob("*_user_*.csv")):
            with f.open(encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    rows.append({
                        "model": r.get("model") or model_key,
                        "thread_id": r.get("thread_id"),
                        "iteration": r.get("iteration"),
                        "query_number": int(_float(r.get("query_number"))),
                        "visual_name": r.get("visual_name") or "(sin visual)",
                        "query": r.get("query") or "",
                        "rows": int(_float(r.get("rows"))),
                        "duration": _float(r.get("duration")),
                        "start_time": _float(r.get("start_time")),
                        "status": (r.get("status") or "ok").strip().lower(),
                        "error": r.get("error") or "",
                    })
        if since_epoch is not None and rows and min(r["start_time"] for r in rows) < since_epoch:
            continue
        err = folder / "error.log"
        error_lines = [ln for ln in err.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()] \
            if err.exists() else []
        runs.append({
            "run_id": folder.name, "model_key": model_key, "level": int(m.group("level")),
            "timestamp": m.group("ts"), "rows": rows, "error_lines": error_lines,
        })
    return sorted(runs, key=lambda r: (r["model_key"], r["level"], r["timestamp"]))


def _visual_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    by: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("status", "ok") == "ok":
            by[r["visual_name"]].append(r["duration"])
    return {v: {"count": len(d), "p50": percentile(d, 50), "p95": percentile(d, 95), "max": max(d)} for v, d in by.items()}


def summarize(runs: list[dict[str, Any]], slow_query_sec: float = 5.0, top: int = 10) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_model[run["model_key"]].append(run)

    models = []
    all_starts, all_ends = [], []
    for model_key, model_runs in sorted(by_model.items()):
        model_runs.sort(key=lambda r: (r["level"], r["timestamp"]))
        per_user_counts = [
            n for run in model_runs for n in _queries_per_user(run["rows"]).values()
        ]
        queries_per_user = max(per_user_counts) if per_user_counts else 0
        levels = []
        for run in model_runs:
            rows = run["rows"]
            ok_rows = [r for r in rows if r["status"] == "ok"]
            durations = [r["duration"] for r in ok_rows]
            starts = [r["start_time"] for r in rows]
            ends = [r["start_time"] + r["duration"] for r in rows]
            expected = run["level"] * queries_per_user
            errored = len(rows) - len(ok_rows)
            missing = (max(0, expected - len(rows)) + errored) if expected else (1 if run["error_lines"] else 0)
            query_errors = list(dict.fromkeys(r["error"] for r in rows if r["status"] != "ok" and r["error"]))
            wall = (max(ends) - min(starts)) if rows else 0.0
            if rows:
                all_starts.append(min(starts))
                all_ends.append(max(ends))
            levels.append({
                "level": run["level"], "run_id": run["run_id"],
                "users_seen": len({r["thread_id"] for r in rows}),
                "queries": len(ok_rows), "recorded_queries": len(rows), "expected_queries": expected,
                "failed_queries": missing, "errored_queries": errored,
                "error_rate": round(missing / expected, 4) if expected else (1.0 if run["error_lines"] else 0.0),
                "error_log_lines": len(run["error_lines"]),
                "error_samples": [_redact(x)[:300] for x in (query_errors + run["error_lines"])[:3]],
                "mean": sum(durations) / len(durations) if durations else None,
                "p50": percentile(durations, 50) if durations else None,
                "p90": percentile(durations, 90) if durations else None,
                "p95": percentile(durations, 95) if durations else None,
                "p99": percentile(durations, 99) if durations else None,
                "max": max(durations) if durations else None,
                "qps": round(len(ok_rows) / wall, 2) if wall > 0 else None,
                "start_utc": _iso(min(starts)) if rows else None,
                "end_utc": _iso(max(ends)) if rows else None,
                "duration_s": round(wall, 1),
            })

        with_rows = [r for r in model_runs if r["rows"]]
        slow_visuals, slow_queries = [], []
        if with_rows:
            first, last = with_rows[0], with_rows[-1]
            v_first, v_last = _visual_stats(first["rows"]), _visual_stats(last["rows"])
            for name, s in sorted(v_last.items(), key=lambda kv: kv[1]["p95"], reverse=True)[:top]:
                base = v_first.get(name, {}).get("p95")
                slow_visuals.append({
                    "visual": name, "level": last["level"], "count": s["count"],
                    "p50": round(s["p50"], 3), "p95": round(s["p95"], 3), "max": round(s["max"], 3),
                    "p95_first_level": round(base, 3) if base is not None else None,
                    "growth": round(s["p95"] / base, 2) if base else None,
                    "slow": s["p95"] >= slow_query_sec,
                })
            by_q: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
            for r in last["rows"]:
                if r["status"] == "ok":
                    by_q[(r["visual_name"], r["query_number"])].append(r)
            ranked = sorted(by_q.items(), key=lambda kv: percentile([x["duration"] for x in kv[1]], 95), reverse=True)
            for (visual, qn), rs in ranked[:5]:
                d = [x["duration"] for x in rs]
                slow_queries.append({
                    "visual": visual, "query_number": qn, "level": last["level"],
                    "p95": round(percentile(d, 95), 3), "mean": round(sum(d) / len(d), 3),
                    "rows": rs[0]["rows"], "dax": " ".join(rs[0]["query"].split())[:600],
                })
        models.append({
            "model_key": model_key,
            "model": next((r["rows"][0]["model"] for r in model_runs if r["rows"]), model_key),
            "queries_per_user": queries_per_user,
            "levels": levels, "slow_visuals": slow_visuals, "slow_queries": slow_queries,
        })
    return {
        "models": models,
        "window": {"start_utc": _iso(min(all_starts)) if all_starts else None,
                   "end_utc": _iso(max(all_ends)) if all_ends else None},
    }


def _queries_per_user(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[str(r["thread_id"])] += 1
    return out


def _redact(text: str) -> str:
    text = re.sub(r"(Password|AccessToken|Token)\s*=\s*[^;]+", r"\1=<redacted>", text, flags=re.I)
    return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<upn>", text)


def evaluation_level(levels: list[dict[str, Any]], target: int) -> dict[str, Any] | None:
    measured = [lv for lv in levels if lv["queries"]]
    if not measured:
        return None
    exact = [lv for lv in measured if lv["level"] == target]
    if exact:
        return exact[-1]
    above = [lv for lv in measured if lv["level"] >= target]
    return min(above, key=lambda lv: lv["level"]) if above else max(measured, key=lambda lv: lv["level"])


def sustained_level(levels: list[dict[str, Any]], cfg: dict[str, Any]) -> int:
    """Mayor nivel de la rampa que cumple p95 y tasa de error (hasta el primer nivel que no cumple)."""
    ok = 0
    for lv in sorted(levels, key=lambda x: x["level"]):
        if lv["queries"] and lv["p95"] is not None and lv["p95"] <= cfg["p95_sec"] and lv["error_rate"] <= cfg["max_error_rate"]:
            ok = lv["level"]
        else:
            break
    return ok


def evaluate_load_test(summary: dict[str, Any] | None, cfg: dict[str, Any]) -> list[Check]:
    c = cfg["load_test"]
    if not summary or not summary.get("models"):
        return [Check("load_test.evidence", "load_test", FAIL, "Sin evidencia del test de carga",
                      "No hay resultados en Files/PerfScenarios/logs para este run. Si la revisión del modelo falló, "
                      "el pipeline no lanza el test (stop_on_review_fail = true).")]
    checks: list[Check] = []
    for m in summary["models"]:
        key = m["model_key"]
        levels = m["levels"]
        tested = sorted(lv["level"] for lv in levels)
        ev = evaluation_level(levels, c["target_level"])
        if ev is None:
            checks.append(Check(f"load_test.{key}.evidence", "load_test", FAIL, f"{key}: ningún nivel con resultados",
                                "Todos los usuarios virtuales fallaron; revisa error.log.",
                                {"errors": [s for lv in levels for s in lv["error_samples"]][:3]}))
            continue
        checks.append(Check(
            f"load_test.{key}.ramp", "load_test",
            WARN if len(tested) < c["min_levels"] or max(tested) < c["target_level"] else PASS,
            f"{key}: cobertura de la rampa",
            f"Niveles probados {', '.join(map(str, tested))}; objetivo {c['target_level']} usuarios.",
            {"levels": tested, "target_level": c["target_level"]},
        ))
        checks.append(Check(
            f"load_test.{key}.p95", "load_test", FAIL if ev["p95"] > c["p95_sec"] else PASS,
            f"{key}: p95 con {ev['level']} usuarios",
            f"p95 {n(ev['p95'], 2)} s (SLO {n(c['p95_sec'])} s).", {"level": ev["level"], "p95": ev["p95"]},
        ))
        checks.append(Check(
            f"load_test.{key}.p50", "load_test", WARN if ev["p50"] > c["p50_sec"] else PASS,
            f"{key}: p50 con {ev['level']} usuarios",
            f"p50 {n(ev['p50'], 2)} s (objetivo {n(c['p50_sec'])} s).", {"level": ev["level"], "p50": ev["p50"]},
        ))
        horizon = max(ev["level"], c["target_level"])
        collapsed = sorted(lv["level"] for lv in levels if lv["level"] <= horizon and not lv["queries"])
        if collapsed:
            checks.append(Check(
                f"load_test.{key}.collapsed", "load_test", FAIL, f"{key}: niveles sin ninguna consulta correcta",
                f"Con {collapsed} usuarios fallaron todos los usuarios virtuales; el p95 se mide en un nivel inferior.",
                {"levels": collapsed, "errors": [s for lv in levels for s in lv["error_samples"]][:3]}))
        upto = [lv for lv in levels if lv["level"] <= horizon]
        failed = sum(lv["failed_queries"] for lv in upto)
        expected = sum(lv["expected_queries"] for lv in upto) or 1
        rate = failed / expected
        checks.append(Check(
            f"load_test.{key}.errors", "load_test", FAIL if rate > c["max_error_rate"] else PASS,
            f"{key}: consultas fallidas hasta {ev['level']} usuarios",
            f"{failed} de {expected} ({pc(rate)}; máximo {pc(c['max_error_rate'], 0)}).",
            {"failed": failed, "expected": expected, "rate": round(rate, 4)},
        ))
        first = next((lv for lv in sorted(levels, key=lambda x: x["level"]) if lv["queries"]), None)
        if first and first["level"] != ev["level"] and first["p95"]:
            growth = ev["p95"] / first["p95"]
            floor = c.get("min_p95_sec_for_growth_check", 0) or 0
            noise = ev["p95"] < floor
            detail = (f"p95 ×{n(growth, 1)} de {first['level']} a {ev['level']} usuarios (máximo ×{n(c['max_p95_growth_ratio'])}).")
            if noise:
                detail += f" Con un p95 de {n(ev['p95'], 2)} s (menos de {n(floor)} s) la degradación no es perceptible y no se evalúa."
            checks.append(Check(
                f"load_test.{key}.scalability", "load_test",
                WARN if growth > c["max_p95_growth_ratio"] and not noise else PASS,
                f"{key}: degradación del p95 con la concurrencia",
                detail,
                {"from_level": first["level"], "to_level": ev["level"], "growth": round(growth, 2)},
            ))
        checks.append(Check(
            f"load_test.{key}.sustained", "load_test", PASS if sustained_level(levels, c) >= c["target_level"] else WARN,
            f"{key}: nivel sostenido dentro del SLO",
            f"{sustained_level(levels, c)} usuarios concurrentes cumplen p95 y errores.",
            {"sustained_level": sustained_level(levels, c)},
        ))
    return checks
