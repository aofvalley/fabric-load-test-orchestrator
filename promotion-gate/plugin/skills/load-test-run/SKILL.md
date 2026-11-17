---
name: load-test-run
description: >-
  Prepara y lanza el test de carga de un modelo semántico con el Fabric Load Test Orchestrator (rampa secuencial
  de usuarios, think times reales de Performance Analyzer, varios modelos en paralelo). Úsala para «graba el
  escenario de Performance Analyzer», «prepara el test de carga», «qué rampa uso», «lanza solo el test de carga»
  o «el test de carga no arranca».
---

# Test de carga (fase 2 del gate)

El motor es el [Fabric Load Test Orchestrator](https://github.com/aofvalley/fabric-load-test-orchestrator)
(extensión no oficial del FabricLoadTestTool de `microsoft/fabric-toolbox`). El gate lo llama con
`ExecutePipeline` sobre `PL_PerfTest_MultiModel_v3` y `test_name_prefix = gate-<run_id>`.

## 1. Escenario de navegación

1. En Power BI Desktop, abre el informe real conectado al modelo del stage de test.
2. View > Performance Analyzer > Start recording. Navega como un usuario: páginas, segmentaciones, drill.
   Haz pausas reales; el orquestador las reproduce como think times.
3. Export > JSON. Un fichero por modelo, sin espacios en el nombre.
4. Súbelo: `smgate upload --workspace-id $env:GATE_WORKSPACE_ID --lakehouse-id $env:GATE_LAKEHOUSE_ID --file <json>`.

Con RLS, el escenario debe ejercitar los roles: pasa UPNs de prueba en `rls_users` o la ruta de un fichero del lakehouse en `rls_users_file` (un UPN por línea; necesitan read y build). El gate traduce eso a `rls_source` y `rls_scope = global` del orquestador 3.3.0.

## 2. Elegir parámetros

| Objetivo | Parámetros |
|---|---|
| Primer run tras desplegar | `ramp_levels=[1,5,10]`, `iterations=1` |
| Gate realista | Rampa que llegue a `target_level` (por ejemplo `[6,20,60]`), `enable_think_times=true`, `think_time_scale=1`, `ramp_up_sec` ≈ un tercio de la duración del escenario |
| Estrés | `enable_think_times=false`, `ramp_up_sec=0`; no lo uses para el veredicto |

Más de 100 usuarios por nivel: sube `vCores` en `%%configure` de `RunLoadTest_v3`; si no, el cuello está en el
generador y el gate lo verá como latencia alta con la capacidad holgada.

## 3. Lanzar solo la carga (sin veredicto)

```powershell
smgate run-item --workspace-id $env:GATE_WORKSPACE_ID --name PL_PerfTest_MultiModel_v3 --wait `
  --param test_name_prefix=gate-<run_id> --param ramp_levels="[6,20,60]" `
  --param models='[{"model_key":"ventas","dataset":"Ventas","workspace":"<ws>","queryfile":"/lakehouse/default/Files/PerfScenarios/Queries/ventas.json"}]'
```

Después, `NB_Gate_LoadTestReport` con el mismo `run_id` (skill `load-test-report`).

## Problemas típicos

| Síntoma | Causa |
|---|---|
| `Navigation file ... not found` | `queryfile` no empieza por `/lakehouse/default/` o el lakehouse por defecto no es el del orquestador |
| Filas con `status = error` | Consultas fallidas (timeout, throttling, RLS); el usuario sigue. Mensaje en la columna `error` y en `error.log` (orquestador 3.4.0 o posterior) |
| Usuarios sin CSV y `error.log` | El usuario virtual no llegó a conectar (permisos, XMLA, nombre del modelo); con versiones anteriores a 3.4.0, cualquier fallo de consulta |
| `WorkspaceNotFound` | Pipeline importado a mano: reinstala con `Setup_LoadTest_v3` |
| Latencias muy bajas y planas | Caché del motor: todos los usuarios repiten las mismas consultas. Graba escenarios con filtros distintos o varios ficheros |
