"""Umbrales del gate. Los valores por defecto viven aquí; `config/gate.yaml` los sobrescribe por clave."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "model_review": {
        "max_errors": 0,  # reglas BPA de severidad Error
        "max_warnings": 30,  # reglas BPA de severidad Warning
        "blocking_rules": [],  # cualquier violación de estas reglas es FAIL, sea cual sea su severidad
        "ignored_rules": [],  # excepciones aceptadas por el equipo (se listan en el informe)
        "sku": "F64",  # SKU de la capacidad de producción, para el límite de memoria por modelo
        "max_model_memory_pct_of_sku": 50,  # tamaño en memoria frente al máximo por modelo del SKU
        "max_column_pct_of_model": 20,  # una sola columna no debería pesar más que esto
        "min_model_mb_for_column_check": 100,  # en modelos pequeños el reparto entre columnas no es significativo
    },
    "load_test": {
        "target_level": 60,  # usuarios concurrentes que el modelo debe sostener en el SLO
        "p50_sec": 1.5,
        "p95_sec": 4.0,
        "max_error_rate": 0.01,  # consultas fallidas o usuarios perdidos sobre lo esperado
        "max_p95_growth_ratio": 3.0,  # p95 al nivel objetivo frente al primer nivel
        "min_p95_sec_for_growth_check": 1.0,  # por debajo, el cociente es ruido de milisegundos y no se evalúa
        "slow_query_sec": 5.0,  # umbral para listar visuales y consultas lentas
        "min_levels": 2,  # rampa mínima para hablar de escalabilidad
    },
    "capacity": {
        "required": True,  # sin evidencia de Capacity Metrics el gate no pasa
        "max_utilization_pct": 80,  # pico de CU % (background + interactivo) en la ventana del test
        "warn_interactive_delay_pct": 80,  # % del umbral de retraso interactivo (100 = se aplica throttling)
        "max_interactive_delay_pct": 100,
        "warn_interactive_rejection_pct": 50,
        "max_model_failed_operations": 0,
        "max_tooling_cu_share_pct": 25,  # CU del propio generador de carga sobre el total de la ventana
    },
    "verdict": {
        "warn_blocks_promotion": False,
    },
}

# Memoria máxima por modelo semántico (GB) por SKU de Fabric.
# Fuente: https://learn.microsoft.com/fabric/enterprise/powerbi/service-premium-what-is#semantic-model-sku-limitation
SKU_MAX_MODEL_MEMORY_GB = {
    "F2": 3, "F4": 3, "F8": 3, "F16": 5, "F32": 10, "F64": 25, "F128": 50,
    "F256": 100, "F512": 200, "F1024": 400, "F2048": 400,
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _read(source: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if source is None or source == "":
        return {}
    if isinstance(source, dict):
        return source
    text = str(source)
    path = Path(text)
    if len(text) < 1024 and path.exists():
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            import yaml

            return yaml.safe_load(raw) or {}
        return json.loads(raw)
    if text.strip().startswith("{"):
        return json.loads(text)
    return {}  # una ruta que no existe (p. ej. gate.yaml aún sin subir): valores por defecto


def load_config(source: str | Path | dict[str, Any] | None = None,
                override: str | dict[str, Any] | None = None) -> dict[str, Any]:
    """Valores por defecto, después `source` (dict, ruta YAML/JSON o texto JSON) y por último `override`.

    Los notebooks pasan `gate.yaml` del equipo como `source` y el parámetro `gate_config` del pipeline como
    `override`: la app o el CI ajustan un run concreto sin perder el resto de umbrales del equipo.
    """
    return _merge(_merge(DEFAULTS, _read(source)), _read(override))
