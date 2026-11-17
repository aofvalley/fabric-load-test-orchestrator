---
name: load-test-report
description: >-
  Interpreta los resultados del test de carga de un modelo semántico y propone mejoras: percentiles por nivel de la
  rampa, consultas fallidas, nivel sostenido dentro del SLO, visuales lentas por consulta o por contención y DAX
  más lento. Úsala para «analiza el test de carga», «por qué falla el p95», «cuántos usuarios aguanta», «qué visual
  optimizo» o «compara este run con el anterior».
---

# Informe del test de carga (fase 3 del gate)

## Obtener los datos

```powershell
smgate fetch --workspace-id $env:GATE_WORKSPACE_ID --lakehouse-id $env:GATE_LAKEHOUSE_ID --run-id <run_id> --out out/<modelo>
```

`loadtest.json` trae por modelo y nivel: consultas correctas, fallidas (filas con `status = error` más las de usuarios que no
llegaron a escribir CSV, frente a usuarios × consultas por usuario),
p50, p90, p95, p99, máximo, QPS y ventana UTC; además las 10 visuales y las 5 consultas DAX más lentas del último nivel.
Para rehacer el análisis con otros umbrales sin tocar Fabric:
`smgate evaluate --loadtest out/<modelo>/loadtest.json --config <otro gate.yaml> --out out/whatif`.

## Cómo leerlo

| Patrón | Lectura | Acción |
|---|---|---|
| p50 y p95 planos al subir usuarios | El modelo absorbe la carga | Nada |
| p50 estable, p95 y máximo crecen | Cola en las consultas pesadas | Optimizar las visuales con más crecimiento |
| Todo crece a la vez | Saturación de capacidad o de modelo | Mirar Capacity Metrics: si hay throttling es capacidad; si no, contención |
| Visual lenta ya con el primer nivel | Problema de la consulta, no de la concurrencia | DAX Studio con Server Timings: SE frente a FE, CallbackDataID, materialización |
| Visual que crece ×3 o más | Contención en el formula engine | Menos iteradores sobre tablas grandes, agregaciones, lógica al origen |
| Consultas fallidas | Usuarios virtuales caídos (timeout, throttling, RLS) | Leer `error_samples`; no comparar latencias hasta corregirlo |
| Latencia alta y capacidad por debajo del 50 % | Posible cuello en el generador | Subir vCores de `RunLoadTest_v3` o repartir usuarios |

«Nivel sostenido» es el mayor nivel de la rampa que cumple p95 y tasa de error sin saltos; si es menor que
`target_level`, el gate falla aunque niveles más altos den mejor p95 por casualidad.

## Para optimizar una consulta

1. Copia el DAX de `slow_queries` del informe.
2. Ejecútalo en DAX Studio contra el modelo de dev con Server Timings y caché limpia.
3. Si quieres ayuda con la medida, usa el agente `pbi-dax` (mide antes y después) o `pbi-rendimiento` para el
   diagnóstico de extremo a extremo.

## Límites

La latencia es la del cliente (incluye red y cola). Los usuarios repiten consultas, así que la caché hace que el
resultado sea optimista. Compara siempre niveles del mismo modelo y runs con el mismo escenario.
