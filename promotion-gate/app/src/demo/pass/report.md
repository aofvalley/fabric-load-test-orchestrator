# Gate de promoción: Ventas

**Veredicto: ✅ PASS**. Listo para promocionar.

Run `demo-20261105-101500`, evaluado 2026-11-05T08:58:45.716054Z, gate 0.1.0.

## Resumen por área

| Área | Estado |
|---|---|
| Revisión del modelo | ✅ PASS |
| Test de carga | ✅ PASS |
| Capacity Metrics | ✅ PASS |

## Comprobaciones

|  | Área | Comprobación | Detalle |
|---|---|---|---|
| ✅ | Revisión del modelo | Reglas BPA de severidad Error | 0 violaciones (máximo 0). |
| ✅ | Revisión del modelo | Reglas BPA de severidad Warning | 1 violaciones (máximo recomendado 30). |
| ✅ | Revisión del modelo | Reglas bloqueantes del equipo | Ninguna regla bloqueante violada. |
| ✅ | Revisión del modelo | Memoria del modelo frente al límite de F64 | 1850 MB = 7 % del máximo por modelo (25 GB). El refresco completo puede necesitar el doble. |
| ✅ | Revisión del modelo | Columnas que dominan el tamaño del modelo | Ninguna por encima del umbral. |
| ✅ | Test de carga | ventas: cobertura de la rampa | Niveles probados 6, 20, 60; objetivo 60 usuarios. |
| ✅ | Test de carga | ventas: p95 con 60 usuarios | p95 3,30 s (SLO 4 s). |
| ✅ | Test de carga | ventas: p50 con 60 usuarios | p50 1,04 s (objetivo 1,5 s). |
| ✅ | Test de carga | ventas: consultas fallidas hasta 60 usuarios | 0 de 258 (0,0 %; máximo 1 %). |
| ✅ | Test de carga | ventas: degradación del p95 con la concurrencia | p95 ×2,6 de 6 a 60 usuarios (máximo ×3). |
| ✅ | Test de carga | ventas: nivel sostenido dentro del SLO | 60 usuarios concurrentes cumplen p95 y errores. |
| ✅ | Capacity Metrics | Pico de utilización de la capacidad | 62,5 % (máximo 80 %); media 38,0 %. |
| ✅ | Capacity Metrics | Throttling interactivo (retraso) | Pico 41,0 % del umbral de retraso (100 % = las consultas interactivas se retrasan). |
| ✅ | Capacity Metrics | Throttling interactivo (rechazo) | Pico 4,0 % del umbral de rechazo (100 % = se rechazan consultas). |
| ✅ | Capacity Metrics | Operaciones fallidas o rechazadas del modelo | 0 fallidas, 0 rechazadas, 0,0 min de throttling (día completo). |
| ✅ | Capacity Metrics | Consumo del propio generador de carga | Los notebooks del test suponen el 6,1 % del CU del día en la capacidad. Si comparten capacidad con el modelo, contaminan la medida. |

## Mejoras recomendadas

| Prioridad | Área | Qué | Acción | Dato |
|---|---|---|---|---|
| Media | Revisión del modelo | BPA: Use the DIVIDE function for division | Usa DIVIDE() en vez del operador / para las divisiones con posible denominador cero. | 1 objeto(s): Margen % (Warning, DAX Expressions) |
| Baja | Revisión del modelo | BPA: Provide format string for measures | Las medidas visibles deberían tener formato. | 1 objeto(s): Ventas (Info, Formatting) |
| Baja | Capacity Metrics | Operación con más CU del modelo: Query | Úsala como línea base de CU para comparar la próxima versión del modelo. | 2800 CU(s) en 2340 operaciones (1,20 CU(s) por operación) |

## Test de carga

Ventana UTC: 2026-10-27T07:33:20Z → 2026-10-27T07:38:56.906000Z.

### Ventas (`ventas`)

| Usuarios | Consultas | Fallidas | p50 s | p90 s | p95 s | máx s | QPS | Duración s |
|---|---|---|---|---|---|---|---|---|
| 6 | 18 | 0 | 0,82 | 1,24 | 1,25 | 1,26 | 2,56 | 7,00 |
| 20 | 60 | 0 | 0,88 | 1,70 | 1,74 | 1,78 | 4,08 | 14,70 |
| 60 | 180 | 0 | 1,04 | 3,10 | 3,30 | 3,50 | 4,88 | 36,90 |

Visuales con más latencia en el último nivel:

| Visual | p95 s | p95 primer nivel s | Crecimiento | Lenta |
|---|---|---|---|---|
| Matriz detalle | 3,43 | 1,26 | 2,73 | no |
| Top clientes | 1,25 | 0,84 | 1,49 | no |
| Ventas por mes | 0,62 | 0,42 | 1,49 | no |

<details><summary>Consultas DAX más lentas</summary>

- **Matriz detalle** (consulta 3): p95 3,43 s, 12 filas

  ```dax
  EVALUATE SUMMARIZECOLUMNS('Fecha'[Mes], "x", [Ventas 3])
  ```

- **Top clientes** (consulta 2): p95 1,25 s, 12 filas

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
| Utilización pico / media % | 62.5 / 38.0 |
| Retraso interactivo pico % umbral | 41,00 |
| Rechazo interactivo pico % umbral | 4,00 |
| Carry-over pico % | 0,00 |
| CU(s) del modelo en el día | 3100,00 |
| CU del generador de carga % del día | 6,10 |

Operaciones del modelo (día completo):

| Operación | CU(s) | Operaciones | CU(s)/op | Fallidas | Rechazadas | Throttling min |
|---|---|---|---|---|---|---|
| Query | 2800,00 | 2340 | 1,20 | 0 | 0 | 0,00 |
| Dataset On-Demand Refresh | 300,00 | 1 | 300,00 | 0 | 0 | 0,00 |

## Revisión del modelo

Tamaño en memoria: 1850.0 MB.

| Tabla | Columna | MB | % modelo | Cardinalidad |
|---|---|---|---|---|
| Hechos | FechaHora | 300,00 | 16,20 | 9000000 |
| Hechos | IdTransaccion | 190,00 | 10,30 | 48000000 |
| Hechos | Importe | 120,00 | 6,50 | 2100000 |
| Cliente | Email | 140,00 | 7,60 | 850000 |

## Límites de la evidencia

- La latencia es la del cliente (notebook): incluye red y cola, no solo el motor.
- Los usuarios repiten las mismas consultas: la caché del motor hace que el resultado sea optimista.
- La tabla diaria de Capacity Metrics suma todo el día; los timepoints sí son de la ventana exacta.
