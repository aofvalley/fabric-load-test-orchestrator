# Revisión del Fabric Load Test Orchestrator (v3.2.0)

Repositorio revisado: [aofvalley/fabric-load-test-orchestrator](https://github.com/aofvalley/fabric-load-test-orchestrator)
(preparado por Pablo Ahumada, fork de `paakos/fabric-load-test-orchestrator`), commit inicial `9fb828f`, etiqueta `v3.2.0`.
Extensión no oficial del FabricLoadTestTool de `microsoft/fabric-toolbox`, licencia MIT.

Objetivo de la revisión: usarlo como motor de carga dentro de un gate de promoción de modelos semánticos de dev a prod.

## Cómo se ha revisado

| Qué | Resultado |
|---|---|
| Lectura de notebooks, pipelines, instalador y docs | Completa |
| Suite del repo (`pytest`, notebooks reales contra Fabric y ADOMD simulados) | **103 tests en verde** en local |
| CSV generados por los notebooks reales leídos por el gate (`promotion_gate.loadtest`) | Compatible: usuarios, consultas por usuario, niveles y percentiles cuadran |
| Ejecución en Fabric real | Pendiente: primer run con `ramp_levels = [1, 5, 10]` (ver [runbook](runbook.md)) |

## Lo que está bien resuelto

- **Rampa secuencial por modelo y modelos en paralelo** con dos pipelines (Fabric no admite `ForEach` dentro de `ForEach`). Es la pieza que faltaba en la herramienta original.
- **Think times reales** a partir de los `User Action` de Performance Analyzer, con escala, tope y jitter, y con prueba de que se aplicaron (consultas 5 y 6 de `AnalyzeLoadTest_v3`).
- **Instalador de un notebook** que resuelve ids del workspace destino y verifica que no queda ningún id ajeno ni placeholder. Evita el clásico `WorkspaceNotFound` de pipelines importados a mano.
- **Higiene**: token redactado en logs, `build_package.py` rechaza zips con ids, correos o tenants, originales intactos en `upstream/`.
- **Tests serios**: ejecutan las celdas reales de los notebooks contra runtimes simulados, no copias de la lógica.

## Hallazgos

| # | Severidad para el gate | Hallazgo | Evidencia | Cómo lo cubre el gate | Propuesta para el acelerador |
|---|---|---|---|---|---|
| 1 | Alta, **PR [#1](https://github.com/aofvalley/fabric-load-test-orchestrator/pull/1)** | No devuelve resultados consumibles: ni `exitValue` ni tabla. Los CSV quedan en `Files/` y la celda final de `RunLoadTest_v3` solo hace `display`. `deltalake` se importa pero no se escribe nada | `RunLoadTest_v3`, celdas 2 y 6 | `NB_Gate_LoadTestReport` resume los CSV en `loadtest.json` y el veredicto los persiste en Delta (`gate_runs`, `gate_checks`) | `notebookutils.notebook.exit()` con un resumen por nivel (p50, p95, consultas, errores) y escritura opcional a Delta |
| 2 | Alta, **PR [#2](https://github.com/aofvalley/fabric-load-test-orchestrator/pull/2)** | Una consulta fallida tumba al usuario virtual entero y pierde todas sus filas: el CSV se escribe al final y la excepción se relanza. Bajo throttling, justo lo que se quiere medir desaparece | `RunPerfScenario_v3`, celda 3 (`raise` tras `error.log`) | La tasa de error se calcula como consultas que faltan frente a usuarios × consultas por usuario, y se leen las líneas de `error.log` (UPN y token redactados) | `try/except` por consulta con columnas `status` y `error`, y escritura del CSV en `finally` |
| 3 | Media | Generador de carga y modelo pueden compartir capacidad: los notebooks de Spark (`runMultiple`, hasta 300) consumen CU y contaminan la medida | Diseño: el instalador despliega en el workspace del lakehouse | `capacity.tooling_share` mide el CU del workspace de herramientas y avisa por encima del 25 % | Documentar como requisito un workspace de herramientas en otra capacidad |
| 4 | Media | Caché del motor: todos los usuarios repiten exactamente las mismas consultas, así que a partir del primer usuario casi todo sale de caché y el resultado es optimista | `load_queries` replica el mismo fichero para todos | Se declara en «Límites de la evidencia» del informe | Varios ficheros por modelo repartidos entre usuarios, o variación de filtros; `ClearCache` opcional entre niveles (requiere admin del modelo) |
| 5 | Media | El cliente puede ser el cuello: 4 vCores por defecto para hasta 300 usuarios; la latencia se mide en el notebook | `RunLoadTest_v3`, celda `%%configure` | Regla del asesor: latencia alta con utilización de capacidad baja apunta al generador | Recomendación de vCores por nivel o aviso cuando `concurrent_threads` supere un umbral con 4 vCores |
| 6 | Baja | `if (i<iterations)` siempre es cierto: hay una espera extra de `delay_sec` tras la última iteración (heredado del original). Alarga cada nivel, no afecta a latencias | `RunPerfScenario_v3`, celda 3 | No aplica | `if i < iterations - 1` |
| 7 | Baja | El parámetro `xmla_endpoint` se ignora: siempre se construye `powerbi://.../myorg/{workspace}` aunque la doc diga «None = endpoint del workspace actual» | `RunPerfScenario_v3`, celda 3 | No aplica | Respetar el parámetro si viene informado |
| 8 | Baja | `RunPerfScenario_v3` mantiene `customdata = "foo"` por defecto (heredado). Desde el pipeline llega `None`, pero en ejecución suelta añade `CustomData=foo` | Celda de parámetros | No aplica | `customdata = None` |

Ninguno impide usarlo como motor del gate. Los hallazgos 1 y 2 ya tienen PR abierto en el acelerador (versión 3.3.0):

| PR | Qué cambia | Efecto en el gate |
|---|---|---|
| [#1](https://github.com/aofvalley/fabric-load-test-orchestrator/pull/1) Resumen por run | `RunLoadTest_v3` escribe `summary.json` por nivel y sale con él (`exitValue`): percentiles de consultas correctas, consultas fallidas, usuarios perdidos, tasa de error y ventana UTC. Con `write_results_to_tables` lo añade a las tablas Delta `loadtest_runs` y `loadtest_queries`. Si `runMultiple` falla, deja igualmente `summary.json` | Cualquier pipeline o herramienta puede leer el resultado de cada nivel sin parsear CSV |
| [#2](https://github.com/aofvalley/fabric-load-test-orchestrator/pull/2) Errores por consulta (apilado sobre #1) | Una consulta fallida es una fila con `status = error` y su mensaje (token redactado); el usuario sigue, la conexión se reabre si se cerró y el CSV se escribe en `finally`. `AnalyzeLoadTest_v3` cuenta fallidas y calcula percentiles solo con las correctas | `promotion_gate.loadtest` ya lee `status` y `error`: tasa de error exacta y percentiles sin la duración de las consultas fallidas. Los CSV de 3.2.0 se siguen leyendo |

| [#3](https://github.com/aofvalley/fabric-load-test-orchestrator/pull/3) Autenticación ADOMD (apilado sobre #2) | `open_adomd_connection` autentica como semantic-link: `refresh_tom_access_token` de `sempy.fabric._client._utils` y callback `OnAccessTokenExpired`, con `EffectiveUserName` intacto. Sin sempy vuelve a `password=`. El token ya no forma parte de la cadena de conexión que se registra | Sin él, en el tenant dev **todas** las consultas fallaban con «Authentication failed for all authenticators» |

Validación de los PR: 121 tests del acelerador en verde y paquete 3.3.0 sin fugas.

### Run en Fabric real (tenant dev, noviembre de 2026)

- Instalado desde la rama del PR #3 con `smgate install-orchestrator` en un workspace de herramientas en F4 (Spain);
  modelo de prueba `Ventas` en otra capacidad (trial).
- **Hallazgo 9 (alta, PR #3):** el token de `notebookutils.credentials.getToken("pbi")` es válido (usuario y audiencia
  correctos), pero ADOMD lo rechaza tanto como `password=` como como `AccessToken`. El de sempy sí entra. Con los PR #1
  y #2 el fallo quedó a la vista (`status=error` en cada fila, `summary.json` con tasa de error 1,0) en lugar de perder
  los usuarios en silencio.
- Con el PR #3: nivel 1 sin errores, `summary.json` leído por el gate.
- Resultado del run completo (rampa 1, 5 y 10, objetivo 10 usuarios): test de carga PASS (0 de 96 consultas fallidas,
  p95 0,18 s con 10 usuarios), Capacity Metrics v53 PASS (27 timepoints en la ventana, sin throttling) y revisión del
  modelo FAIL por la regla bloqueante «Do not use floating point data types» (`Importe`, `Precio Lista`). Veredicto FAIL
  correcto: el modelo no debe promocionarse hasta cambiar esas columnas a decimal fijo.
- Ajustes del gate que salieron del run real: v53 devuelve `Timepoints[Timepoint]` (antes se descartaban todas las
  filas), `smgate run-item` envía objetos como texto JSON, y los modelos de menos de 100 MB no evalúan el reparto por
  columna. La tabla diaria por item de Capacity Metrics todavía no mostraba las consultas del modelo una hora después
  del test; los timepoints sí.

## Requisitos que impone al gate

- El gate se despliega en **el mismo workspace y lakehouse** que el orquestador: lee los CSV de `Files/PerfScenarios/logs/` y llama a `PL_PerfTest_MultiModel_v3` por id.
- `test_name_prefix = gate-<run_id>` aísla cada ejecución del gate; `model_key` solo admite letras, dígitos, `-` y `_`.
- Pipelines y notebooks se pasan parámetros por nombre exacto: Fabric ignora los desconocidos sin avisar. El test `test_pipeline_forwards_only_known_orchestrator_parameters` lo vigila.
