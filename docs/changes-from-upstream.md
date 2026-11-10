# Changes from the original tool

Baseline: [`tools/FabricLoadTestTool`](https://github.com/microsoft/fabric-toolbox/tree/5012e9b76c478b7dba4d7b2dc58248fbf38e4b45/tools/FabricLoadTestTool)
of `microsoft/fabric-toolbox` at commit `5012e9b76c478b7dba4d7b2dc58248fbf38e4b45`, kept unmodified in [`upstream/`](../upstream).

Compare them yourself with, for example:
`git diff --no-index upstream/RunPerfScenario.ipynb notebooks/RunPerfScenario_v3.ipynb` (or an ipynb-aware diff tool).

## `RunLoadTest.ipynb` → `notebooks/RunLoadTest_v3.ipynb`

| Area | Original | v3 |
|---|---|---|
| Parameters | Imports, parameters and the main logic are in **one cell**, so a pipeline cannot inject values | Parameters live in their own cell tagged **Parameters**; the pipeline's values are injected below it (`concurrent_threads`, `dataset`, `queryfile`, ...) |
| Validation | None | Types are normalised; ranges are checked (`1 ≤ concurrent_threads ≤ 300`, jitter between 0 and 1, no negatives); missing navigation file gives a clear error |
| Run identifier | `<name>-<timestamp>` | `<name>-c<concurrent_threads>-<timestamp>`, so each ramp level has its own folder |
| Virtual users | Started together | `start_delay_sec = ramp_up_sec × i / concurrent_threads` is passed to every user (staggered start) |
| RLS | Users list edited in the code | `rls_source` (`list`, `file`, `none`) and `rls_scope` (`global`, `per_model`): UPNs from `rls_users`, from a text file (`rls_users_file`) or from each model's `users` / `users_file`, spread across the virtual users |
| New parameters | – | `enable_think_times`, `think_time_scale`, `max_think_time_sec`, `think_time_jitter_pct`, `fallback_think_time_sec`, `ramp_up_sec`, `initial_user_jitter_sec`, `rls_source`, `rls_scope`, `rls_users`, `rls_users_file`, `model_settings`, `stop_on_query_error`, `fail_on_error_rate`, `write_results_to_tables` |
| Callee | `RunPerfScenario` | `RunPerfScenario_v3` |
| Result consolidation | Kept | Kept (same polars aggregation cell) |
| Results for other tools | `display` of a polars frame; `deltalake` imported but not used | `summary.json` per run and the same summary as the notebook **exit value**; optional Delta tables `loadtest_runs` and `loadtest_queries` (`write_results_to_tables`) |

Everything that the original does with `notebookutils.notebook.runMultiple` (one activity per virtual user, DAG concurrency =
number of users) is kept.

## `RunPerfScenario.ipynb` → `notebooks/RunPerfScenario_v3.ipynb`

| Area | Original | v3 |
|---|---|---|
| Wait between queries | `delay_sec` after **every** query | Unchanged when `enable_think_times = False` (default). When `True`, the pauses between *user actions* recorded in the Performance Analyzer file are replayed and `delay_sec` applies only between iterations |
| Query loading | Flat list of DAX queries | Each query also carries its user action and the recorded pause before that action (`load_queries`, tested against the original loader) |
| Think-time controls | – | `think_time_scale`, `max_think_time_sec`, `think_time_jitter_pct`, `fallback_think_time_sec` |
| Start | All users immediately | `start_delay_sec` (set by `RunLoadTest_v3`) plus optional random `initial_user_jitter_sec` |
| Logging | CSV with one row per query | Same CSV, plus `logs/<loadtestId>/thinktimes/*_thinktimes.csv` with the recorded, scaled and applied pause of every action (only when think times are enabled) |
| Security | The connection string, which carries the access token, is printed and written to `error.log` | The token is replaced by `<redacted-token>` in console output and `error.log` |
| Failed query | The exception ends the virtual user; its CSV is written only at the end, so **all** its rows are lost | The query is a row with `status = error`, `rows = 0` and the error message (token redacted); a line is added to `error.log`, the connection is reopened if it was closed and the user goes on |
| CSV writing | After the last iteration | In `finally`: the rows already measured are written even if the user stops early. The `DataReader` is always closed |
| CSV writing | Default file opening | `newline=''`, so multi-line DAX text keeps a stable CSV format |
| Code structure | Single flow | Think-time logic is in a cell that depends only on the standard library, so it is unit-tested without Fabric |

The ADOMD connection, the role/`CustomData`/`EffectiveUserName` handling and the CSV columns of the original are kept.

## New components

| Component | Purpose |
|---|---|
| `pipelines/PL_PerfTest_Ramp_v3.json` | One model: sequential `ForEach` over `ramp_levels`, each calling `RunLoadTest_v3` with `concurrent_threads = @item()` |
| `pipelines/PL_PerfTest_MultiModel_v3.json` | Parallel `ForEach` over `models`, each running the child pipeline |
| `notebooks/AnalyzeLoadTest_v3.ipynb` | DuckDB analysis of the result CSV files (ramp, think times, parallel models, latency) |
| `installer/Setup_LoadTest_v3.ipynb` + `tools/build_package.py` | Deploy to any workspace without hard-coded ids |
| `tests/` | Executes the real notebook cells against fake runtimes |

## What is intentionally not changed

- The DAX replay, the XMLA/ADOMD connection and the CSV result schema.
- `runMultiple` as the way to start virtual users.
- Default behaviour of the notebooks when run by hand: think times are **off**, so the results are comparable with the original.
