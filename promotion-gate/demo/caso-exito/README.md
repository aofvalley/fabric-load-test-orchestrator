# Caso de éxito: Ventas Retail

Un modelo semántico listo para producción, con su informe y su recorrido de navegación, para enseñar el gate con un
resultado apto. Se crea en el workspace que indiques, dentro de la carpeta **Ventas Retail**. Ponlo en **otra capacidad**
que la del workspace del gate: así el CU del generador de carga no se mezcla con el del modelo, igual que en producción.

| Item | Qué es |
|---|---|
| `lh_ventas_retail` | Lakehouse con esquemas. Estrella en `dbo`: `fact_ventas` (2 M de líneas), `dim_fecha`, `dim_tienda`, `dim_producto` y `dim_canal`. Datos ficticios de enero de 2024 a octubre de 2026 |
| `NB_Ventas_Retail_VOrder` | Reescribe las tablas con V-Order (delta-rs no lo escribe y Direct Lake lo necesita) |
| `Ventas Retail` (modelo) | Direct Lake. Claves enteras ocultas y sin MDX, importes en decimal fijo, relaciones de un solo sentido, tabla de fechas marcada, medidas con `DIVIDE`, formato y descripción en todo lo visible |
| `Ventas Retail` (informe) | PBIR de tres páginas: Resumen (con segmentador de año), Tiendas y Productos |

El escenario de navegación (`Ventas_Retail_informe.json`) se sube a `Files/PerfScenarios/Queries/` del lakehouse del
gate. Reproduce un usuario que abre el resumen, filtra 2026, revisa tiendas y productos, con pausas de 8 a 14 s: 19
consultas, las mismas que lanzan los visuales del informe, validadas contra el modelo antes de subirlas.

## Por qué pasa el gate

- **Buenas prácticas:** 0 hallazgos de BPA. Lo que suele fallar y aquí está resuelto: importes en `decimal` (no
  `double`), claves de relación enteras, ninguna relación bidireccional, claves ocultas con `isAvailableInMdx: false`,
  formatos `#,0`, `#,0.0` y `#,0.0%;-#,0.0%;#,0.0%`, descripciones y tablas Delta con V-Order.
- **Carga:** medidas aditivas simples sobre una estrella pequeña; ningún visual agrupa por una columna de alta
  cardinalidad (el error de AdventureWorks con Customer ID).

## Generarlo

Necesita Python x64 con `numpy`, `pandas`, `pyarrow`, `deltalake` y `httpx` (en Windows ARM64, con uv:
`uv venv .venv-demo --python cpython-3.12-windows-x86_64-none`).

```powershell
python demo\caso-exito\build.py --workspace-id <workspace del modelo> --gate-workspace-id <workspace del gate> `
  --gate-lakehouse-id <lh_gate> --subscription <sub>
# por pasos: --only data | vorder | model | report | scenario
```

O, más sencillo, `deploy/deploy.ps1 ... -SuccessCase -SuccessCaseWorkspace <workspace del modelo>`.

Después, en la app: modelo **Ventas Retail**, «Reutilizar un escenario ya subido» con `Ventas_Retail_informe.json`,
rampa 6, 20 y 60, y «Lanzar gate». O por CLI con `smgate run`.

## Resultado (tenant dev, 6 de noviembre de 2026)

**PASS, promocionable**, en 26 minutos de punta a punta, con el gate en una F4 y el modelo en una F8:

| Área | Resultado |
|---|---|
| Buenas prácticas | 0 errores, 0 avisos, ninguna regla bloqueante |
| Test de carga, rampa 6, 20 y 60 | 1.634 consultas sin errores; p95 0,09 s, 0,10 s y 0,88 s (SLO 4 s); sostiene los 60 usuarios objetivo |
| Capacity Metrics | Pico de utilización 37,5 % de la F8, sin throttling; 0 % de CU del generador en la capacidad del modelo |

Dos comprobaciones salen como omitidas, y es lo correcto: el tamaño VertiPaq (sempy no informa tamaños de un modelo
Direct Lake aunque la revisión lo caliente) y las operaciones del modelo por item, que Capacity Metrics publica con
más retraso que la utilización.
