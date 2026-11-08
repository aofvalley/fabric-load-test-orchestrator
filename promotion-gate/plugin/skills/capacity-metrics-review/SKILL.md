---
name: capacity-metrics-review
description: >-
  Extrae y explica lo que dice el modelo semántico de la app Fabric Capacity Metrics durante el test de carga de un
  modelo: utilización, throttling (retraso y rechazo interactivo), carry-over, CU por operación del modelo,
  operaciones fallidas o rechazadas y consumo del propio generador de carga. Úsala para «revisa Capacity Metrics del
  test», «hubo throttling», «cuánto CU consume el modelo», «Capacity Metrics no tiene datos» o para dimensionar el SKU.
---

# Capacity Metrics (fase 4 del gate)

`NB_Gate_CapacityMetrics` consulta el modelo semántico de la app con `sempy.fabric.evaluate_dax`. Las consultas son
las de FUAM (`microsoft/fabric-toolbox`), con detección de la versión de la app (v40, v44, v47 y v53).

## Qué extrae

| Dato | Tabla de la app | Granularidad |
|---|---|---|
| Utilización (background + interactivo) | `TimePoints` y `'All Measures'` | 30 s, ventana exacta del test ± 5 min |
| Retraso y rechazo interactivo, rechazo background | `'All Measures'[Dynamic ... %]` | 30 s |
| Carry-over acumulado | `'All Measures'[Cumulative carry over %]` | 30 s |
| CU, duración, operaciones, fallidas, rechazadas y throttling del modelo por operación | `'Metrics By Item Operation And Day'` | Día |
| CU de los items del workspace de herramientas (notebooks del orquestador) | Misma tabla, filtrada por workspace | Día |

Retraso al 100 % significa que Fabric ya retrasa las consultas interactivas; rechazo al 100 %, que las rechaza.

## Lanzar o repetir esta fase

La app tarda de 10 a 15 minutos en reflejar el consumo. Si el informe dice «sin datos en la ventana», repite solo
esta fase y el veredicto con el mismo `run_id`:

```powershell
smgate run-item --workspace-id $env:GATE_WORKSPACE_ID --name NB_Gate_CapacityMetrics --wait --param run_id=<run_id> `
  --param capacity_metrics_workspace="$env:CAPACITY_METRICS_WORKSPACE" --param model_workspace="<workspace>"
smgate run-item --workspace-id $env:GATE_WORKSPACE_ID --name NB_Gate_Verdict --wait --param run_id=<run_id> --param dataset="<modelo>"
```

## Consultas a mano

`smgate capacity-dax --probes` imprime las sondas de versión; `smgate capacity-dax --version v53 --capacity-id <id>
--date 2026-11-04` las consultas del gate. Puedes ejecutarlas con la herramienta ExecuteQuery del servidor
MCP de Power BI o FabricIQ contra el modelo «Fabric Capacity Metrics» para profundizar (por ejemplo, otro día como
línea base).

## Cómo leerlo

- Throttling durante el test: la capacidad no aguanta la carga prevista. Optimiza las operaciones con más CU antes
  de escalar el SKU; para proteger producción, valora surge protection.
- Utilización alta sin throttling: el smoothing lo absorbe hoy; mira el carry-over.
- `tooling.share_pct` alto: el generador comparte capacidad con el modelo y contamina la medida. Mueve el
  workspace del orquestador a otra capacidad.
- CU(s) por operación «Query» es la línea base para comparar la siguiente versión del modelo.
- La tabla diaria suma todo el día: si hubo otra actividad sobre el modelo, el CU no es solo del test.

Para una lectura por consulta (CPU por query, fallback de Direct Lake), activa Workspace Monitoring y usa el agente
`pbi-rendimiento`.
