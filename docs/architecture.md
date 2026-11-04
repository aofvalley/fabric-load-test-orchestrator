# Architecture

## Execution flow

```text
PL_PerfTest_MultiModel_v3
└─ ForEach_Models            parallel, batchCount = 10
   └─ ExecutePipeline → PL_PerfTest_Ramp_v3        waitOnCompletion = true
      └─ ForEach_Ramp        sequential
         └─ Notebook RunLoadTest_v3                concurrent_threads = @item()
            └─ runMultiple (concurrency = concurrent_threads)
               ├─ RunPerfScenario_v3  user 0   start_delay = ramp_up_sec × 0 / N
               ├─ RunPerfScenario_v3  user 1   start_delay = ramp_up_sec × 1 / N
               └─ ...
```

- **Models run in parallel** (the parent's `ForEach` is not sequential). Each model has its own run folders, so results never mix.
- **Levels of one model run sequentially**: level *n+1* starts only after level *n* finished (`isSequential = true`).
- **Users of one level run in parallel**, optionally with a staggered start.

### Why two pipelines

Fabric does not allow a `ForEach` inside another `ForEach`. The parent iterates over models and delegates the ramp to the child
with an `ExecutePipeline` activity, which works inside the same workspace without creating a connection.

### Why a parameters cell and arrays stay in the pipeline

Notebook parameters accept only `int`, `float`, `bool` and `string`. The array of levels therefore lives in the pipeline
(`ramp_levels`) and the notebook receives one integer per iteration.

## Items and placeholders

| Item | Type | Placeholders in the repository |
|---|---|---|
| `RunPerfScenario_v3` | Notebook | – |
| `RunLoadTest_v3` | Notebook | – |
| `AnalyzeLoadTest_v3` | Notebook | – |
| `PL_PerfTest_Ramp_v3` | Pipeline | `{{WORKSPACE_ID}}`, `{{NOTEBOOK:RunLoadTest_v3}}` |
| `PL_PerfTest_MultiModel_v3` | Pipeline | `{{PIPELINE:PL_PerfTest_Ramp_v3}}` |

The installer creates the notebooks first, then the child pipeline, then the parent, replacing every placeholder with the id of the item
in the target workspace. Notebooks are bound to the default lakehouse of the installer (same workspace).

## Results on disk

```text
Files/PerfScenarios/logs/
└─ <test_name_prefix>-<model_key>-c<N>-<yyyymmdd-hhmmss>/
   ├─ <loadtestId>_user_<k>.csv           one row per query executed (start_time, duration, model, thread_id, status, error, ...)
   ├─ summary.json                        one summary of the run, also the exit value of RunLoadTest_v3 (see below)
   ├─ error.log                           one line per failed query, and the error of a user that could not connect
   └─ thinktimes/<loadtestId>_user_<k>_thinktimes.csv   (only with enable_think_times = true)
```

## Run summary and exit value

At the end of every run `RunLoadTest_v3` writes `summary.json` in the run folder and exits with the same JSON, so a pipeline
can read it as `activity('RunLoadTest_v3').output.result.exitValue`:

| Field | Meaning |
|---|---|
| `status` | `completed`, `completed_with_errors` (failed queries or lost virtual users) or `failed` (`runMultiple` failed or no results) |
| `users_with_results`, `missing_users` | Virtual users that wrote a CSV file; the others failed before running any query |
| `queries`, `failed_queries`, `expected_queries`, `error_rate` | `expected = users × queries per user`; `error_rate = (failed + queries of lost users) / expected` |
| `mean_s`, `p50_s`, `p90_s`, `p95_s`, `p99_s`, `max_s` | Latency of the successful queries |
| `qps`, `start_utc`, `end_utc`, `duration_s` | Throughput and time window of the run (UTC, for example to query the Capacity Metrics app) |
| `error_log_lines`, `run_error` | Lines in `error.log` and the error of `runMultiple`, if any |

When `runMultiple` fails, `summary.json` is still written (with `run_error`) before the notebook fails, so the evidence of
the users that did finish is kept. With `write_results_to_tables = true` the summary is appended to the Delta table
`loadtest_runs` and every query to `loadtest_queries` (explicit schemas, `mergeSchema` on).

## Test strategy

| Layer | How it is tested |
|---|---|
| Think-time parser and helpers | Pure unit tests, plus a comparison with the original `load_queries` |
| `RunPerfScenario_v3` | The real cells are executed with fake `notebookutils`, `sempy` and ADOMD modules |
| `RunLoadTest_v3` | The real cells are executed with a fake `runMultiple` that checks the DAG it receives; the summary cells run over CSV files written by the real scenario notebook, with a fake Spark for the Delta tables |
| `AnalyzeLoadTest_v3` | Executed over CSV files produced by the scenario notebook (two models in parallel, two ramp levels) |
| Installer | Executed against an in-memory fake of the Fabric REST API (dry run, deploy, re-run, overwrite, invalid models, tampered zip, foreign ids) |
| Package | Hash and leak checks, pipeline/notebook parameter consistency, untouched `upstream/` files |

The tests cannot prove the behaviour of the real Fabric service; run a small ramp (`[1, 5, 10]`) after deploying.
