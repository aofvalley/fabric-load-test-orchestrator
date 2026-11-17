# Runbook del gate de promoción

## Antes de la demo

1. Capacidades del workspace de herramientas y del de la app activas (si están en pausa, `deploy.ps1` lo dice y para).
2. `pwsh deploy/deploy.ps1 -ToolsWorkspace ... -AppWorkspace ... -CapacityMetricsWorkspace ... -WhatIf` y, si el plan
   cuadra, sin `-WhatIf`: orquestador, gate, app y, con `-SuccessCase`, el modelo Ventas Retail. Unos 9 minutos.
3. Abrir la app desde `app_portal` (en `deploy/.deployment.json`), iniciar sesión y comprobar que lista los workspaces.
4. Para un modelo propio: su JSON de Performance Analyzer, subido desde la app o con `smgate upload`.

Si `az` tiene por defecto otra cuenta (por ejemplo, un invitado del tenant sin acceso a los workspaces), pasa
`-Subscription` o `-Tenant` al script; para `smgate`, exporta `SMGATE_AZ_SUBSCRIPTION` o `SMGATE_AZ_TENANT`.

Qué capturar antes: SKU y utilización de la capacidad del modelo en la última hora (Capacity Metrics) y la versión
del modelo que se va a probar (commit o despliegue del stage de test).

## Demo

1. En la Fabric App (`app/`): elegir workspace, modelo e informe, subir la grabación de Performance Analyzer (o generar el escenario sintético), rampa `[1,5,10]` para la demo y «Lanzar gate». Alternativa por chat: en Copilot CLI o Claude Code con el plugin, «el modelo Ventas está listo para producción, pasa el gate».
2. El agente comprueba requisitos y lanza `smgate run ... --wait` con una rampa corta (`[1,5,10]`) para la demo.
3. Mientras corre: enseñar en Fabric el pipeline `PL_PromotionGate` y los CSV que aparecen en `Files/PerfScenarios/logs/gate-<run_id>-*`.
4. Veredicto: abrir `out/<modelo>/report.md` y enseñar comprobaciones, mejoras priorizadas y la tabla por nivel.
5. Con FAIL: aplicar una mejora (por ejemplo, la regla de floating point en dev), repetir solo la fase afectada con `smgate run-item` o el gate completo.
6. Con PASS: `smgate promote --dry-run` y, con OK, la promoción real; o enseñar el workflow de CI con aprobación del environment `production`.
7. Cerrar con las tablas `gate_runs` y `gate_checks` como histórico de promociones.

Qué capturar después: `report.md` y `verdict.json` del run, captura del pipeline en Fabric y de Capacity Metrics en la ventana del test.

## Teardown

`pwsh deploy/teardown.ps1 -ToolsWorkspace ... [-AppWorkspace ... -App] -WhatIf` lista los items del gate (y de la app);
sin `-WhatIf` los borra tras escribir el nombre del workspace. No borra el orquestador, el lakehouse, los runs
(`Files/PromotionGate`) ni las tablas `gate_*`: son auditoría. Entre demos basta con pausar las capacidades.

## Coste

| Recurso | SKU | Coste aproximado | Entre demos |
|---|---|---|---|
| Capacidad del workspace de herramientas (Spark del orquestador y notebooks del gate) | F8 o superior; F16 para rampas de 100+ usuarios | F8 ≈ 1,44 $/h, F16 ≈ 2,88 $/h en PAYG (precio de lista US, varía por región) | Pausar la capacidad |
| Capacidad del modelo | La de producción prevista (p. ej. F64) | La que ya exista | Pausar si es de laboratorio |
| Capacity Metrics, CI | App gratuita; runners estándar | 0 € | Nada |

Un gate con rampa `[6,20,60]`, 1 iteración y think times dura unos 25 a 30 minutos. Medido en F4 (40 min antes de
quitar la espera fija):

| Fase | Duración | Qué pesa |
|---|---|---|
| Buenas prácticas | 2 min | BPA, VertiPaq y, en Direct Lake frío, el calentado de columnas |
| Test de carga | 18 a 19 min | Por nivel: unos 2 min de sesión Spark, la carga real (0,7, 1,6 y 2,6 min) y, con 60 usuarios, unos 4 min arrancando 60 notebooks hijos |
| Informe de carga | 1 min | |
| Capacity Metrics | 2 a 8 min | Sondeo cada 2 min hasta que los timepoints cubren el final del test (máximo `metrics_lag_minutes`, 20) |
| Veredicto | 1 min | |

Probado y descartado: compartir una sesión Spark de alta concurrencia entre niveles (`sessionTag`). Ahorra el arranque
de los niveles 2 y siguientes, pero `runMultiple` reparte peor los usuarios virtuales en esa sesión: 20 usuarios pasaron
de 4,4 a 8,7 minutos. Además, con la alta concurrencia para pipelines activada, `%pip` no funciona; por eso los
notebooks del gate cargan su wheel con `sys.path` y no con `%pip`.
