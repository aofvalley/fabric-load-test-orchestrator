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
   ├─ <loadtestId>_user_<k>.csv           one row per query executed (start_time, duration, model, thread_id, ...)
   └─ thinktimes/<loadtestId>_user_<k>_thinktimes.csv   (only with enable_think_times = true)
```

## Test strategy

| Layer | How it is tested |
|---|---|
| Think-time parser and helpers | Pure unit tests, plus a comparison with the original `load_queries` |
| `RunPerfScenario_v3` | The real cells are executed with fake `notebookutils`, `sempy` and ADOMD modules |
| `RunLoadTest_v3` | The real cells are executed with a fake `runMultiple` that checks the DAG it receives |
| `AnalyzeLoadTest_v3` | Executed over CSV files produced by the scenario notebook (two models in parallel, two ramp levels) |
| Installer | Executed against an in-memory fake of the Fabric REST API (dry run, deploy, re-run, overwrite, invalid models, tampered zip, foreign ids) |
| Package | Hash and leak checks, pipeline/notebook parameter consistency, untouched `upstream/` files |

The tests cannot prove the behaviour of the real Fabric service; run a small ramp (`[1, 5, 10]`) after deploying.
