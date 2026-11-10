# Fabric Load Test Orchestrator

Pipeline-driven orchestration for the **FabricLoadTestTool** of
[`microsoft/fabric-toolbox`](https://github.com/microsoft/fabric-toolbox/tree/main/tools/FabricLoadTestTool):
test several Power BI semantic models **in parallel**, ramp the number of concurrent users **sequentially**
(for example 6 → 20 → 60 → 100 → 200 → 300), replay the **think times** recorded in Performance Analyzer, and deploy everything
to any workspace with **one installer notebook**.

> **Unofficial.** This is a community extension built on top of the original tool. It is not an official Microsoft project and is not
> supported by Microsoft. See [NOTICE.md](NOTICE.md) for the attribution and [upstream/](upstream) for the untouched originals.

## What it adds to the original tool

| Original (`RunLoadTest` / `RunPerfScenario`) | This repository |
|---|---|
| One model and one concurrency level per notebook run; `concurrent_threads` is edited by hand | A **pipeline** passes `concurrent_threads` to the notebook at run time, so a `ForEach` can run a whole ramp |
| One model per run | A parent pipeline runs **N models in parallel** (`ForEach`, at most 10 at a time) |
| `delay_sec` after every query | Optional **think-time replay**: the pauses between user actions recorded in the Performance Analyzer file (scale, cap, jitter) |
| All users start at once | Optional **staggered start** (`ramp_up_sec`) and random initial offset (`initial_user_jitter_sec`) |
| Users hard-coded in a cell | RLS identities from a **list** (`rls_users`) or a **text file** (`rls_users_file`), for all models or **one per model** (`rls_source`, `rls_scope`) |
| Access token printed in logs | Token **redacted** in console output and `error.log` |
| A failed query ends the virtual user and loses all its rows | The failed query is a row with `status = error`; the user goes on and its CSV is always written |
| Manual import of every item | **Installer notebook** + zip: resolves workspace, lakehouse, notebook and pipeline ids for the target workspace and verifies the result |
| Results only as CSV files and a `display` | Every run ends with **`summary.json`** and returns it as the notebook **exit value** (p50, p95, failed queries, lost users); optional Delta tables `loadtest_runs` and `loadtest_queries` |
| – | **Analysis notebook** (DuckDB) with nine queries that prove the ramp, the think times and the parallelism |
| – | Test suite that runs the real notebooks against a fake ADOMD/Fabric runtime |

The complete list of changes against the original is in [docs/changes-from-upstream.md](docs/changes-from-upstream.md).

## Architecture

```text
PL_PerfTest_MultiModel_v3                         parent pipeline
└─ ForEach_Models            (parallel, batchCount 10)   one item per semantic model
   └─ ExecutePipeline → PL_PerfTest_Ramp_v3       child pipeline
      └─ ForEach_Ramp        (sequential)                one item per level: 6, 20, 60, ...
         └─ Notebook RunLoadTest_v3                       concurrent_threads = @item()
            └─ notebookutils.notebook.runMultiple
               └─ RunPerfScenario_v3 × N virtual users    think times, staggered start, CSV logs
```

Two pipelines are needed because Fabric does not allow a `ForEach` inside another `ForEach`. Details in
[docs/architecture.md](docs/architecture.md).

## Repository layout

```text
notebooks/      RunPerfScenario_v3, RunLoadTest_v3, AnalyzeLoadTest_v3  (source of truth, English)
pipelines/      PL_PerfTest_Ramp_v3.json, PL_PerfTest_MultiModel_v3.json (with {{placeholders}} resolved by the installer)
installer/      Setup_LoadTest_v3.ipynb  (deploys the package into the workspace where it runs)
tools/          build_package.py (builds dist/FabricLoadTest_v3_package.zip), make_sample_data.py
samples/        sample_performance_data.json (synthetic), models.example.json, models.rls.example.json, users.example.txt
tests/          pytest suite
docs/           architecture, deployment, parameters, analysis, changes from upstream, Spanish guide (docs/es)
upstream/       exact copies of the original files (do not edit)
```

## Quick start

Prerequisites: a Fabric workspace on a capacity, a **lakehouse in that workspace**, one or more Power BI semantic models,
a Performance Analyzer export (JSON) per model, and the **XMLA read endpoint enabled** on the capacity. Contributor role or
higher in the workspace.

1. **Get the package.** Download `FabricLoadTest_v3_package.zip` and `Setup_LoadTest_v3.ipynb` from the
   [Releases](../../releases) page, or build them: `python tools/build_package.py`.
2. **Import** `Setup_LoadTest_v3.ipynb` into the target workspace and attach the lakehouse as its **default** lakehouse.
3. **Upload** the zip to `Files/deploy/` of that lakehouse.
4. In the Parameters cell set `MODELS` (or leave `None` and edit the pipeline later) and run with `DRY_RUN = True` first,
   then `DRY_RUN = False`. The installer ends with a verification that every id belongs to the workspace.
5. **Upload one Performance Analyzer JSON per model** to `Files/PerfScenarios/Queries/`. For RLS, upload the users files (one UPN per line)
   to `Files/PerfScenarios/Users/` and choose `rls_source` / `rls_scope`.
6. Open `PL_PerfTest_MultiModel_v3`, press **Run**, fill in `models`. The default ramp is the safe `[1, 5, 10]`; change
   `ramp_levels` to `[6, 20, 60, 100, 200, 300]` for a real run.
7. Run `AnalyzeLoadTest_v3` to check the ramp, the think times and the parallelism.

Full steps and troubleshooting: [docs/deployment.md](docs/deployment.md).

### `models` parameter

```json
[
  {"model_key": "SalesA", "dataset": "Sales A", "workspace": "",
   "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/PowerBIPerformanceData_SalesA.json"},
  {"model_key": "SalesB", "dataset": "Sales B", "workspace": "",
   "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/PowerBIPerformanceData_SalesB.json"}
]
```

`model_key` is a short unique label (letters, digits, `-`, `_`) used in the result folder names. `dataset` is the exact name of the
semantic model. An empty `workspace` means the current workspace. Each item may also carry `users` or `users_file` for per-model RLS
identities. See [samples/models.example.json](samples/models.example.json), [samples/models.rls.example.json](samples/models.rls.example.json)
and [RLS identities](docs/parameters.md#rls-identities).

## Main parameters

| Parameter | Default (pipeline) | Meaning |
|---|---|---|
| `ramp_levels` | `[1, 5, 10]` | Concurrent users per level, run one after another for each model |
| `iterations` | `1` | Times each user repeats the recorded scenario |
| `delay_sec` | `4` | Wait between iterations of one user |
| `enable_think_times` | `true` | Replay the recorded pauses between user actions |
| `think_time_scale` | `1.0` | `1.0` recorded pace, `0.5` twice as fast, `0` no pauses |
| `think_time_jitter_pct` | `0.1` | ±10 % random variation of each pause |
| `ramp_up_sec` | `0` | Window over which the users of one level start (`0` = all at once) |
| `initial_user_jitter_sec` | `0` | Random extra delay (0..N s) before each user's first action |
| `rls_source` | `list` | Where the RLS identities come from: `list`, `file` (text file, one UPN per line) or `none` |
| `rls_scope` | `global` | `global`: same identities for every model; `per_model`: `users` / `users_file` in each `models` item |
| `rls_users` | empty | Global list of UPNs to impersonate (`EffectiveUserName`), comma-separated |
| `rls_users_file` | empty | Global text file with the UPNs, e.g. `/lakehouse/default/Files/PerfScenarios/Users/users.txt` |
| `stop_on_query_error` | `false` | `true`: a virtual user stops at its first failed query (behaviour before 3.4.0). By default the failed query is a `status = error` row and the user goes on |
| `fail_on_error_rate` | `1.0` | Fail the notebook when the run's error rate (0 to 1) is above it. `1.0` never fails, `0` fails on any failed query |
| `write_results_to_tables` | `false` | Also append each run to the Delta tables `loadtest_runs` and `loadtest_queries` |

All parameters, their effect and recommendations: [docs/parameters.md](docs/parameters.md). Field-by-field reference of the
`PL_PerfTest_MultiModel_v3` pipeline, with ready-to-paste examples: [docs/pipeline-parameters.md](docs/pipeline-parameters.md).

## Verify what ran

`AnalyzeLoadTest_v3` reads the CSV files written under `Files/PerfScenarios/logs/` and shows, among other things, that every
level had the expected number of distinct users, that levels of one model did not overlap, that models did overlap each other, and
that the measured wait between actions matches the think time that was applied. See [docs/analysis.md](docs/analysis.md).

## Development

```powershell
pip install -r requirements-dev.txt
pytest                       # runs the real notebooks against fake Fabric/ADOMD runtimes, no Fabric needed
python tools/build_package.py
```

The package builder refuses to produce a zip that contains workspace/item ids, e-mail addresses, `onmicrosoft.com` tenants, saved
outputs or lakehouse bindings. Use `--deny-file` to add your own strings to block.

## Limitations

- At most 300 concurrent users per level (validated in `RunLoadTest_v3`); the Spark session size (`%%configure vCores`) limits what
  is practical. See the notes in the notebook.
- At most 10 models in parallel (`batchCount` of `ForEach_Models`, edit it in the pipeline to lower it).
- Pipeline parameters must be passed with exactly these names; unknown names are ignored by Fabric without warning.
- The installer binds the notebooks to a lakehouse of the **same** workspace.

## Attribution and license

Derived from **FabricLoadTestTool** in [`microsoft/fabric-toolbox`](https://github.com/microsoft/fabric-toolbox), MIT License,
Copyright (c) Microsoft Corporation. This repository is released under the MIT License as well, see [LICENSE](LICENSE)
and [NOTICE.md](NOTICE.md).
