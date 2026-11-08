---
name: promotion-gate
description: >-
  Orquesta el gate de promoción de un modelo semántico de Power BI o Fabric de dev a prod. Úsala cuando el equipo
  diga que su modelo está listo para promocionar, «pasa el gate», «¿puedo subir el modelo X a producción?»,
  «lanza la validación de promoción» o «promociona el modelo». Ejecuta revisión de buenas prácticas, test de carga,
  informe con mejoras y lectura de Capacity Metrics, y solo promociona con veredicto favorable y OK explícito.
---

# Gate de promoción de modelos semánticos

Si el equipo prefiere interfaz gráfica, la Fabric App del gate (`app/` de la PoC) hace el mismo recorrido; esta skill es la vía por chat y CI. Un modelo pasa a producción cuando cuatro evidencias, sacadas del mismo run, dan un veredicto PASS (o WARN si el
equipo lo admite en `config/gate.yaml`). Todo corre en Fabric con `PL_PromotionGate`; tú preparas, lanzas, lees y
explicas. La lógica de decisión está en el paquete `promotion_gate` y no se negocia en el chat.

| Fase | Pieza en Fabric | Evidencia | Skill de detalle |
|---|---|---|---|
| 1. Buenas prácticas | `NB_Gate_ModelReview` (semantic-link-labs BPA y VertiPaq) | `model_review.json` | `model-bpa-review` |
| 2. Test de carga | `PL_PerfTest_MultiModel_v3` del Fabric Load Test Orchestrator | CSV en `Files/PerfScenarios/logs/gate-<run_id>-*` | `load-test-run` |
| 3. Informe de carga | `NB_Gate_LoadTestReport` | `loadtest.json` | `load-test-report` |
| 4. Capacity Metrics | `NB_Gate_CapacityMetrics` | `capacity.json` | `capacity-metrics-review` |
| Veredicto | `NB_Gate_Verdict` | `verdict.json`, `report.md`, tablas `gate_runs` y `gate_checks` | esta |

## 1. Recoge lo imprescindible

Pregunta solo lo que no esté en `deploy/.deployment.json` (lo escribe `deploy/deploy.ps1`: `tools_workspace_id`,
`lakehouse_id`, `capacity_metrics_workspace`) o en el `.env` (`DEPLOYMENT_PIPELINE_ID`...):

- Nombre exacto del modelo (`dataset`) y workspace donde vive en el stage de test (`model_workspace`).
- El JSON de Performance Analyzer con la navegación real de los usuarios. Sin él no hay test de carga: ver `load-test-run`.
- Usuarios concurrentes que debe aguantar en producción (`load_test.target_level`) y la rampa (`ramp_levels`), que debe llegar a ese nivel.
- Si el modelo usa RLS: UPNs de prueba para `rls_users`, o un fichero del lakehouse con un UPN por línea para `rls_users_file` (no los escribas en ficheros versionados).

## 2. Comprobaciones previas (no lances nada si falla una)

1. `az account show` coincide con el tenant del `.env`.
2. El orquestador y el gate están desplegados en el workspace de herramientas:
   `smgate deploy --workspace-id $env:GATE_WORKSPACE_ID --lakehouse-id $env:GATE_LAKEHOUSE_ID --dry-run`.
3. El workspace de herramientas está en **otra capacidad** que el modelo. Si no, avisa: los notebooks de Spark
   consumen CU de la misma capacidad y contaminan la medida (el gate lo detecta con `capacity.tooling_share`).
4. La identidad tiene Contributor en el workspace del modelo (BPA y VertiPaq leen el TOM) y lectura en el de Capacity Metrics.
5. El JSON de Performance Analyzer está subido (`smgate upload ... --dest Files/PerfScenarios/Queries/`).

## 3. Lanza el gate

```powershell
smgate run --workspace-id $env:GATE_WORKSPACE_ID --lakehouse-id $env:GATE_LAKEHOUSE_ID --wait --out out/<modelo> `
  --param dataset="<modelo>" --param model_workspace="<workspace test>" --param model_key=<clave_sin_espacios> `
  --param queryfile=/lakehouse/default/Files/PerfScenarios/Queries/<fichero>.json `
  --param ramp_levels="[6,20,60]" --param capacity_metrics_workspace="$env:CAPACITY_METRICS_WORKSPACE"
```

Duración típica: revisión 3 a 8 min, rampa según niveles e iteraciones, espera de Capacity Metrics con sondeo cada 2 min
(máximo `metrics_lag_minutes`, 20 por defecto) y veredicto 2 min. Avisa al usuario y no hagas polling ruidoso.

## 4. Lee y explica

Abre `out/<modelo>/report.md` y responde con: veredicto, las comprobaciones en FAIL o WARN con su dato y las
3 mejoras de prioridad alta. Separa evidencia (lo que dice el informe) de hipótesis (tu interpretación).
Si una fase no tiene evidencia, dilo y propón repetir solo esa fase con `smgate run-item` (ver la skill de la fase).

## 5. Promoción

Solo con `promotable: true` y OK explícito del usuario para ese modelo y ese run:

```powershell
smgate promote --verdict out/<modelo>/verdict.json --deployment-pipeline-id $env:DEPLOYMENT_PIPELINE_ID `
  --source-stage-id $env:STAGE_TEST_ID --target-stage-id $env:STAGE_PROD_ID --dry-run
```

Enseña el dry run, pide confirmación y repite sin `--dry-run`. En equipos con CI, la promoción la hace el workflow
`ci/github/promotion-gate.yml` con aprobación del environment `production`: recomiéndalo frente a la promoción manual.

## Reglas

- Nunca relajes umbrales ni añadas `ignored_rules` para que pase: eso va en un PR a `config/gate.yaml` con justificación.
- Nunca promociones con FAIL, sin evidencia de alguna fase o con un `verdict.json` de otro modelo.
- No borres runs ni tablas `gate_*`: son la auditoría de promociones.
- Los UPN de RLS y los ids reales van al `.env` o a parámetros, nunca a ficheros versionados.
