> Ejemplo generado con datos sintéticos (`python tools/make_demo_evidence.py`). No es un run real.

# Gate de promoción: Ventas

**Veredicto: ❌ FAIL**. No se puede promocionar todavía.

Run `demo-20261104-101500`, evaluado 2026-11-05T08:58:45.445823Z, gate 0.1.0.

## Resumen por área

| Área | Estado |
|---|---|
| Revisión del modelo | ❌ FAIL |
| Test de carga | ❌ FAIL |
| Capacity Metrics | ❌ FAIL |

## Comprobaciones

|  | Área | Comprobación | Detalle |
|---|---|---|---|
| ✅ | Revisión del modelo | Reglas BPA de severidad Error | 0 violaciones (máximo 0). |
| ✅ | Revisión del modelo | Reglas BPA de severidad Warning | 4 violaciones (máximo recomendado 30). |
| ❌ | Revisión del modelo | Reglas bloqueantes del equipo | Do not use floating point data types |
| ✅ | Revisión del modelo | Memoria del modelo frente al límite de F64 | 3200 MB = 12 % del máximo por modelo (25 GB). El refresco completo puede necesitar el doble. |
| ⚠️ | Revisión del modelo | Columnas que dominan el tamaño del modelo | Hechos[IdTransaccion] 34,4 % |
| ✅ | Test de carga | ventas: cobertura de la rampa | Niveles probados 6, 20, 60; objetivo 60 usuarios. |
| ❌ | Test de carga | ventas: p95 con 60 usuarios | p95 13,37 s (SLO 4 s). |
| ✅ | Test de carga | ventas: p50 con 60 usuarios | p50 1,04 s (objetivo 1,5 s). |
| ❌ | Test de carga | ventas: consultas fallidas hasta 60 usuarios | 10 de 258 (3,9 %; máximo 1 %). |
| ⚠️ | Test de carga | ventas: degradación del p95 con la concurrencia | p95 ×6,4 de 6 a 60 usuarios (máximo ×3). |
| ⚠️ | Test de carga | ventas: nivel sostenido dentro del SLO | 6 usuarios concurrentes cumplen p95 y errores. |
| ❌ | Capacity Metrics | Pico de utilización de la capacidad | 86,4 % (máximo 80 %); media 51,0 %. |
| ⚠️ | Capacity Metrics | Throttling interactivo (retraso) | Pico 92,0 % del umbral de retraso (100 % = las consultas interactivas se retrasan). |
| ✅ | Capacity Metrics | Throttling interactivo (rechazo) | Pico 12,0 % del umbral de rechazo (100 % = se rechazan consultas). |
| ❌ | Capacity Metrics | Operaciones fallidas o rechazadas del modelo | 3 fallidas, 0 rechazadas, 1,5 min de throttling (día completo). |
| ✅ | Capacity Metrics | Consumo del propio generador de carga | Los notebooks del test suponen el 7,5 % del CU del día en la capacidad. Si comparten capacidad con el modelo, contaminan la medida. |

## Mejoras recomendadas

| Prioridad | Área | Qué | Acción | Dato |
|---|---|---|---|---|
| Alta | Revisión del modelo | BPA: Do not use floating point data types | Cambia las columnas Double a Decimal fijo (Currency) o entero: comprimen mejor y evitan errores de redondeo. ([doc](https://learn.microsoft.com/power-bi/connect-data/desktop-data-types)) | 2 objeto(s): 'Hechos'[Importe], 'Hechos'[Coste] (Warning, Performance) |
| Alta | Revisión del modelo | BPA: Set IsAvailableInMdx to false on non-attribute columns | Pon IsAvailableInMDX = false en columnas que no se usan como atributo: reduce memoria y procesado. | 1 objeto(s): 'Hechos'[IdTransaccion] (Warning, Performance) |
| Alta | Revisión del modelo | Columna pesada Hechos[IdTransaccion] | Quítala si no se usa; si es clave de texto o GUID, sustitúyela por un entero; si es fecha y hora, sepárala; reduce decimales. | 1100 MB, 34,4 % del modelo, cardinalidad 48000000 |
| Alta | Test de carga | ventas: «Matriz detalle» se degrada con la concurrencia | Contención: la consulta pasa mucho tiempo en el formula engine (un hilo por consulta). Reduce iteradores sobre tablas grandes, materializa en el origen o usa agregaciones; mira Server Timings en DAX Studio. | p95 2,10 s → 13,88 s (×6,6) con 60 usuarios |
| Alta | Test de carga | ventas: sostiene 6 usuarios de 60 | Optimiza las consultas de la lista y repite la rampa; si ya están optimizadas, dimensiona el SKU con la utilización medida en Capacity Metrics. | p95 13,37 s con 60 usuarios |
| Alta | Test de carga | ventas: consultas fallidas en la rampa | Timeouts o rechazos por throttling. Corrige antes de comparar latencias; con el orquestador anterior a 3.4.0 un usuario que falla pierde todas sus filas. | AdomdErrorResponseException: The operation was throttled; user <upn>; Data Source=powerbi://api.powerbi.com/v1.0/myorg/ws;Password=<redacted>;EffectiveUserName=<upn>  : The operation was throttled |
| Alta | Capacity Metrics | Capacidad al límite durante el test | Optimiza las operaciones con más CU del modelo; si es carga legítima, escala el SKU o activa surge protection para proteger los informes interactivos. ([doc](https://learn.microsoft.com/fabric/enterprise/surge-protection)) | pico 86,4 % |
| Alta | Capacity Metrics | Throttling interactivo cerca o activo | El smoothing de 10 minutos ya no absorbe la carga: reduce CU por consulta o reparte el pico. ([doc](https://learn.microsoft.com/fabric/enterprise/throttling)) | retraso interactivo 92,0 % del umbral |
| Media | Revisión del modelo | BPA: Use the DIVIDE function for division | Usa DIVIDE() en vez del operador / para las divisiones con posible denominador cero. | 1 objeto(s): Margen % (Warning, DAX Expressions) |
| Baja | Revisión del modelo | BPA: Provide format string for measures | Las medidas visibles deberían tener formato. | 1 objeto(s): Ventas (Info, Formatting) |
| Baja | Capacity Metrics | Operación con más CU del modelo: Query | Úsala como línea base de CU para comparar la próxima versión del modelo. | 5100 CU(s) en 2280 operaciones (2,24 CU(s) por operación) |

## Test de carga

Ventana UTC: 2026-10-26T07:33:20Z → 2026-10-26T07:39:14.500000Z.

### Ventas (`ventas`)

| Usuarios | Consultas | Fallidas | p50 s | p90 s | p95 s | máx s | QPS | Duración s |
|---|---|---|---|---|---|---|---|---|
| 6 | 18 | 0 | 0,82 | 2,07 | 2,08 | 2,10 | 2,29 | 7,90 |
| 20 | 60 | 0 | 0,88 | 4,52 | 4,64 | 4,76 | 3,39 | 17,70 |
| 60 | 170 | 10 | 1,04 | 12,61 | 13,37 | 14,13 | 3,12 | 54,50 |

Visuales con más latencia en el último nivel:

| Visual | p95 s | p95 primer nivel s | Crecimiento | Lenta |
|---|---|---|---|---|
| Matriz detalle | 13,88 | 2,10 | 6,62 | sí |
| Top clientes | 1,23 | 0,84 | 1,47 | no |
| Ventas por mes | 0,62 | 0,42 | 1,47 | no |

<details><summary>Consultas DAX más lentas</summary>

- **Matriz detalle** (consulta 3): p95 13,88 s, 12 filas

  ```dax
  EVALUATE SUMMARIZECOLUMNS('Fecha'[Mes], "x", [Ventas 3])
  ```

- **Top clientes** (consulta 2): p95 1,23 s, 12 filas

  ```dax
  EVALUATE SUMMARIZECOLUMNS('Fecha'[Mes], "x", [Ventas 2])
  ```

- **Ventas por mes** (consulta 1): p95 0,62 s, 12 filas

  ```dax
  EVALUATE SUMMARIZECOLUMNS('Fecha'[Mes], "x", [Ventas 1])
  ```

</details>

## Capacity Metrics

| Métrica | Valor |
|---|---|
| Versión del modelo de la app | v53 |
| Timepoints en la ventana | 42 |
| Utilización pico / media % | 86.4 / 51.0 |
| Retraso interactivo pico % umbral | 92,00 |
| Rechazo interactivo pico % umbral | 12,00 |
| Carry-over pico % | 4,00 |
| CU(s) del modelo en el día | 5400,00 |
| CU del generador de carga % del día | 7,50 |

Operaciones del modelo (día completo):

| Operación | CU(s) | Operaciones | CU(s)/op | Fallidas | Rechazadas | Throttling min |
|---|---|---|---|---|---|---|
| Query | 5100,00 | 2280 | 2,24 | 3 | 0 | 1,50 |
| Dataset On-Demand Refresh | 300,00 | 1 | 300,00 | 0 | 0 | 0,00 |

## Revisión del modelo

Tamaño en memoria: 3200.0 MB.

| Tabla | Columna | MB | % modelo | Cardinalidad |
|---|---|---|---|---|
| Hechos | IdTransaccion | 1100,00 | 34,40 | 48000000 |
| Hechos | FechaHora | 420,00 | 13,10 | 9000000 |
| Hechos | Importe | 310,00 | 9,70 | 2100000 |
| Cliente | Email | 140,00 | 4,40 | 850000 |

## Límites de la evidencia

- La latencia es la del cliente (notebook): incluye red y cola, no solo el motor.
- Los usuarios repiten las mismas consultas: la caché del motor hace que el resultado sea optimista.
- La tabla diaria de Capacity Metrics suma todo el día; los timepoints sí son de la ventana exacta.
