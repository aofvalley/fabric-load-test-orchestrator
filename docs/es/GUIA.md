# Guía de uso (español)

> Resumen en español del repositorio. La documentación completa está en inglés en [../../README.md](../../README.md) y en [../](..).
> Proyecto no oficial, derivado de **FabricLoadTestTool** de [`microsoft/fabric-toolbox`](https://github.com/microsoft/fabric-toolbox).

## Qué permite hacer

- Probar **varios modelos semánticos en paralelo** con un pipeline padre (`PL_PerfTest_MultiModel_v3`).
- Para cada modelo, ejecutar una **rampa de usuarios concurrentes** de forma **secuencial** (por ejemplo 6, 20, 60, 100, 200, 300) con un pipeline hijo (`PL_PerfTest_Ramp_v3`). El pipeline pasa `concurrent_threads` al notebook en tiempo de ejecución.
- Reproducir los **think times** (pausas entre acciones del usuario) grabados con Performance Analyzer.
- Escalonar el arranque de los usuarios (`ramp_up_sec`) y añadir un desfase aleatorio inicial (`initial_user_jitter_sec`).
- Usar RLS con `rls_source` (`list`, `file`, `none`) y `rls_scope` (`global`, `per_model`): los UPN pueden ir en el parámetro `rls_users`, en un **archivo de texto** (`rls_users_file`, un UPN por línea) o **por modelo** (`users` / `users_file` dentro de cada elemento de `models`).
- **Desplegar en cualquier workspace** con un notebook instalador y un zip, sin ids fijos.
- Medir errores de verdad: una consulta que falla (timeout, throttling, RLS) queda como fila con `status = error` y el usuario virtual sigue; su CSV se escribe siempre, aunque el usuario se detenga. Con `stop_on_query_error = true` el usuario se detiene en su primera consulta fallida, como antes de la 3.4.0. Ojo: una ejecución en verde puede tener consultas fallidas; míralo en `failed_queries` y `error_rate` de `summary.json`, o fija `fail_on_error_rate` (de 0 a 1) para que el notebook falle por encima de ese porcentaje de errores.
- Analizar los resultados con `AnalyzeLoadTest_v3` (nueve consultas).
- Consumir los resultados desde otras herramientas: cada ejecución deja `summary.json` (p50, p95, consultas fallidas, usuarios perdidos) y lo devuelve como *exit value* del notebook; con `write_results_to_tables = true` también se añade a las tablas Delta `loadtest_runs` y `loadtest_queries` (se escriben con `deltalake` en la ruta de OneLake, porque el notebook es Python y no Spark; las columnas nuevas se fusionan en tablas existentes).

## Arquitectura

```text
PL_PerfTest_MultiModel_v3
└─ ForEach_Models (paralelo, máx. 10)          un elemento por modelo semántico
   └─ ExecutePipeline → PL_PerfTest_Ramp_v3
      └─ ForEach_Ramp (secuencial)              un elemento por nivel
         └─ Notebook RunLoadTest_v3             concurrent_threads = @item()
            └─ runMultiple → RunPerfScenario_v3 × N usuarios virtuales
```

Son dos pipelines porque Fabric no permite un `ForEach` dentro de otro `ForEach`.

## Despliegue

1. Descarga `FabricLoadTest_v3_package.zip` y `Setup_LoadTest_v3.ipynb` de *Releases* (o ejecuta `python tools/build_package.py`).
2. Importa `Setup_LoadTest_v3.ipynb` en el workspace destino y asócialo a un **lakehouse del mismo workspace** como lakehouse predeterminado.
3. Sube el zip a `Files/deploy/` del lakehouse.
4. En la celda *Parameters* define `MODELS` (o déjalo en `None`) y ejecuta primero con `DRY_RUN = True` y después con `DRY_RUN = False`.
5. Sube un JSON de Performance Analyzer por modelo a `Files/PerfScenarios/Queries/`.
6. Abre `PL_PerfTest_MultiModel_v3`, pulsa *Run* y rellena `models`. La rampa por defecto es `[1, 5, 10]`; para una prueba real usa `[6, 20, 60, 100, 200, 300]`.

Requisitos: endpoint de lectura XMLA habilitado en la capacidad y permisos de lectura y *build* sobre cada modelo.

## Parámetro `models`

```json
[
  {"model_key": "VentasA", "dataset": "Ventas A", "workspace": "",
   "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/PowerBIPerformanceData_VentasA.json"}
]
```

- `model_key`: etiqueta corta y única (letras, dígitos, `-` y `_`), forma parte del nombre de las carpetas de resultados.
- `dataset`: nombre **exacto** del modelo semántico.
- `workspace`: vacío = el workspace actual.
- `users` / `users_file` (opcionales): usuarios RLS de ese modelo (lista o archivo), para `rls_scope = per_model`.

## Usuarios RLS (`EffectiveUserName`)

| `rls_source` | `rls_scope = global` (por defecto) | `rls_scope = per_model` |
|---|---|---|
| `list` (por defecto) | `rls_users` para todos los modelos | `users` del modelo; si no tiene, `rls_users` |
| `file` | `rls_users_file` para todos los modelos | `users_file` del modelo; si no tiene, `rls_users_file` |
| `none` | sin suplantación | sin suplantación |

Archivo de usuarios: un UPN por línea; se ignoran líneas vacías y comentarios `#`, se eliminan duplicados y una línea no válida se rechaza indicando su número.
Súbelos a `Files/PerfScenarios/Users/`. Con los valores por defecto no se suplanta a nadie (se usa la identidad que ejecuta la prueba). El log indica
cuántas identidades hay y de dónde salen, pero nunca los UPN. Cada usuario necesita permisos de lectura y *build* sobre el modelo.

## Parámetros de think times y rampa

| Parámetro | Efecto |
|---|---|
| `think_time_scale` | Multiplica cada pausa grabada (`1.0` ritmo real, `0.5` el doble de rápido, `0` sin pausas) |
| `max_think_time_sec` | Tope de una pausa individual (se aplica antes del jitter) |
| `think_time_jitter_pct` | Variación aleatoria de cada pausa (`0.1` = ±10 %) para que los usuarios no vayan sincronizados |
| `ramp_up_sec` | Ventana en la que arrancan los usuarios de un nivel: el usuario *i* de *N* espera `ramp_up_sec × i / N` |
| `initial_user_jitter_sec` | Espera aleatoria adicional (0..N s) antes de la primera acción de cada usuario |
| `delay_sec` | Pausa entre iteraciones (con think times activos ya no se aplica tras cada consulta) |

## Pruebas y autoría

`pytest` ejecuta los notebooks reales contra entornos simulados. Los archivos originales sin modificar están en [`upstream/`](../../upstream).
Licencia MIT; véase [../../NOTICE.md](../../NOTICE.md).
