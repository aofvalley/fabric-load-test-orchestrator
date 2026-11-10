# PL_PerfTest_MultiModel_v3: parameter reference

`PL_PerfTest_MultiModel_v3` is the pipeline you run. It starts **one ramp per semantic model, all models in parallel** (at most 10 at a
time, `batchCount` of `ForEach_Models`). For each model, `PL_PerfTest_Ramp_v3` runs the concurrency levels **one after another**, and each
level calls `RunLoadTest_v3`, which starts the virtual users.

```text
PL_PerfTest_MultiModel_v3  ──ForEach (parallel)──►  PL_PerfTest_Ramp_v3  ──ForEach (sequential)──►  RunLoadTest_v3  ──►  N × RunPerfScenario_v3
        models[]                                          ramp_levels[]                                  concurrent_threads = level
```

## Rules that apply to every parameter

- **Names must match exactly** (lower case, underscores). When you run or schedule the pipeline, a parameter with an unknown name is
  **ignored without any warning**.
- Parameters you do not set keep the **default value stored in the pipeline**. The installer can change some defaults (`MODELS`, `RLS_*`).
- `models` and `ramp_levels` are **arrays** (JSON). Paste them as JSON in the *Run* pane or in the schedule.
- Paths are paths **inside the default lakehouse of the notebooks**, written as `/lakehouse/default/...`, with no spaces.
- The notebooks only run one model at one level; everything else is decided here.

## Quick reference

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| [`models`](#models) | Array of objects | one `CHANGE_ME_*` placeholder | The semantic models to test, one ramp each |
| [`test_name_prefix`](#test_name_prefix) | String | `ramp-v3` | Prefix of the result folders |
| [`ramp_levels`](#ramp_levels) | Array of integers | `[1, 5, 10]` | Concurrent users of each level, run sequentially |
| [`iterations`](#iterations) | Int | `1` | Times each user repeats the recorded scenario |
| [`delay_sec`](#delay_sec) | Int | `4` | Wait between iterations |
| [`enable_think_times`](#think-times) | Bool | `true` | Replay the pauses between user actions |
| [`think_time_scale`](#think-times) | Float | `1.0` | Multiplier of every recorded pause |
| [`max_think_time_sec`](#think-times) | Float | `60.0` | Cap of one pause |
| [`think_time_jitter_pct`](#think-times) | Float | `0.1` | Random variation of each pause |
| [`fallback_think_time_sec`](#think-times) | Float | `0.0` | Pause between queries when the file has no user actions |
| [`ramp_up_sec`](#ramp_up_sec-and-initial_user_jitter_sec) | Float | `0.0` | Window in which the users of one level start |
| [`initial_user_jitter_sec`](#ramp_up_sec-and-initial_user_jitter_sec) | Float | `0.0` | Random extra delay before each user's first action |
| [`rls_source`](#rls-identities) | String | `list` | Where the impersonated users come from: `list`, `file`, `none` |
| [`rls_scope`](#rls-identities) | String | `global` | `global` or `per_model` |
| [`rls_users`](#rls-identities) | String | empty | Global list of UPNs, comma-separated |
| [`rls_users_file`](#rls-identities) | String | empty | Global text file with the UPNs |
| [`stop_on_query_error`](#results) | Bool | `false` | `true`: a virtual user stops at its first failed query (behaviour before 3.4.0) |
| [`fail_on_error_rate`](#results) | Float | `1.0` | Fail the run when its error rate (0 to 1) is above it |
| [`write_results_to_tables`](#results) | Bool | `false` | Also append each run to the Delta tables `loadtest_runs` and `loadtest_queries` |

## `models`

An array with **one object per semantic model**. Every object is processed in parallel by the parent pipeline.

```json
[
  {
    "model_key": "SalesA",
    "dataset": "Sales A",
    "workspace": "",
    "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/PowerBIPerformanceData_SalesA.json",
    "users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_SalesA.txt"
  }
]
```

| Field | Required | What it expects |
|---|---|---|
| `model_key` | yes | A **short, unique label** for the model: letters, digits, `-` and `_`, no spaces. It becomes part of the run name and folder, `<test_name_prefix>-<model_key>-c<level>-<timestamp>`, and of the log columns. The installer rejects anything else. It is **not** the model name. |
| `dataset` | yes | The **exact display name** of the semantic model (for example `AdventureWorks Sales`). The notebook uses it as the XMLA *Initial Catalog*, so a different spelling fails with a connection error. |
| `workspace` | yes (may be empty) | The **display name** of the workspace that contains the semantic model, **not its GUID**. Leave it as `""` to use the workspace where the test runs. The notebook builds the XMLA address `powerbi://api.powerbi.com/v1.0/myorg/<workspace>` from this text and does not translate ids, so a GUID is not supported. Use a name for models that live in another workspace; the identity that runs the test needs read and build permission on that model. |
| `queryfile` | yes | Path of the **Performance Analyzer export** (JSON) of that model, in the default lakehouse, starting with `/lakehouse/default/`, no spaces. The run fails immediately if the file does not exist. Use one file per model: each model has its own visuals and queries. |
| `users` | no | List of UPNs for this model (`["a@contoso.com", "b@contoso.com"]`, or a comma-separated string). Used only with `rls_source = list` **and** `rls_scope = per_model`. |
| `users_file` | no | Path of a users text file for this model. Used only with `rls_source = file` **and** `rls_scope = per_model`. |

Notes:

- A `models` entry that omits `users` / `users_file` is valid. With `per_model` it falls back to the global value.
- The whole object of each model is passed to the child pipeline as JSON (`model_settings`), so extra keys are tolerated and ignored.
- The default (`CHANGE_ME_*`) is a placeholder: **replace it** before running.

## `test_name_prefix`

Text that starts the name of every run: `<test_name_prefix>-<model_key>-c<users>-<yyyymmdd-hhmmss>`. Result files are written to
`Files/PerfScenarios/logs/<run name>/`. Keep the default `ramp-v3` if you use `AnalyzeLoadTest_v3` without changes; otherwise set its
`RUN_PREFIX` to the same value. Use a different prefix per test campaign to keep the results apart.

## `ramp_levels`

Array of integers: the number of **concurrent virtual users** of each level, for example `[6, 20, 60, 100, 200, 300]`.

- Levels run **sequentially** for each model: a level starts only when the previous one finishes.
- The same array applies to every model; models run their ramps in parallel with each other.
- Each value must be between **1 and 300**. A larger or smaller value fails at the start of that level.
- The default `[1, 5, 10]` is a safe first run. Large levels need a bigger Spark session: raise `vCores` in the `%%configure` cell of
  `RunLoadTest_v3`.

## `iterations`

Integer. Times each virtual user plays the whole recorded scenario (all actions of the Performance Analyzer file) during its level.

## `delay_sec`

Integer, seconds. With think times **on**, it is the wait **between iterations** of one user. With think times **off**, it is also
the wait after every query (the behaviour of the original tool).

## Think times

A Performance Analyzer file records the **user actions** (a click, a slicer change) and the DAX queries each action triggered. The time
between the end of one action and the start of the next is the user's *think time*.

| Parameter | Expects | Effect |
|---|---|---|
| `enable_think_times` | `true` / `false` | `true`: replay one pause per action. `false`: no pauses between actions, only `delay_sec` (stress style). |
| `think_time_scale` | number ≥ 0 | Multiplies every recorded pause. `1.0` recorded pace, `0.5` twice as fast, `2.0` twice as slow, `0` no pauses. |
| `max_think_time_sec` | number ≥ 0 | Upper limit of one pause **after** scaling, so a recorded 5-minute break does not stall the test. |
| `think_time_jitter_pct` | number from `0` to `1` | Random variation of each pause: `0.1` = between 90 % and 110 %. `0` makes runs repeatable. |
| `fallback_think_time_sec` | number ≥ 0 | Pause between queries when the file has no `User Action` events. |

Applied pause = `min(recorded × think_time_scale, max_think_time_sec) × random(1 − jitter, 1 + jitter)`.

## `ramp_up_sec` and `initial_user_jitter_sec`

Both shape **how the users of one level start**; neither is the ramp of levels (that is `ramp_levels`).

| Parameter | Expects | Effect |
|---|---|---|
| `ramp_up_sec` | number ≥ 0 | Window over which a level's users start. User *i* of *N* waits `ramp_up_sec × i / N`. With 60 s and 6 users they start at 0, 10, 20, 30, 40 and 50 s. `0` starts everyone at once. |
| `initial_user_jitter_sec` | number ≥ 0 | Adds a random 0…N s wait before each user's first action, so the start is not a perfect grid. |

## RLS identities

Row-level security is tested by impersonating users with `EffectiveUserName`. Two switches decide **where the users come from**
(`rls_source`) and **which models they apply to** (`rls_scope`).

| Parameter | Expects | Effect |
|---|---|---|
| `rls_source` | `list`, `file` or `none` | `list`: users written as text (`rls_users`, or `users` in each model). `file`: users read from a text file (`rls_users_file`, or `users_file` in each model). `none`: no impersonation at all. |
| `rls_scope` | `global` or `per_model` | `global`: the same users for every model. `per_model`: each model uses its own `users` / `users_file`. |
| `rls_users` | UPNs separated by commas or semicolons | The global list. |
| `rls_users_file` | `/lakehouse/default/...` path | The global file. |

### Which value is used

| `rls_source` | `rls_scope = global` | `rls_scope = per_model` |
|---|---|---|
| `list` | `rls_users` for every model | `users` of the model; if the model has none, `rls_users` |
| `file` | `rls_users_file` for every model | `users_file` of the model; if the model has none, `rls_users_file` |
| `none` | no impersonation | no impersonation |

Behaviour that is the same in every case:

- **Default = no impersonation.** With `list`, `global` and an empty `rls_users`, the identity that runs the test is used, as in the original tool.
- Users are assigned to the virtual users **in turn** (`user[i mod number_of_users]`). With more virtual users than users, identities are reused.
- With `file`, the run **fails before sending any query** if no file is given, the file does not exist, or it contains no users. An invalid line is
  reported with its line number.
- The log states **how many** users were found and **where they come from**; it never prints the UPNs.
- Every user must exist in the tenant and have **read and build** permission on the model; otherwise the queries of that virtual user fail.
- With a very long list, prefer a file: the model object is passed to the notebook as a text parameter.

### Users file format

```text
# one user principal name per line
user1@contoso.com
user2@contoso.com   # trailing comments are fine
```

Blank lines and `#` comments are ignored, commas or semicolons also separate users, duplicates are removed ignoring case (the first spelling is
kept), and a UTF-8 BOM is accepted. Store the files in `Files/PerfScenarios/Users/` of the lakehouse. See
[samples/users.example.txt](../samples/users.example.txt).

### How to toggle: recipes

Set these parameters when you run the pipeline (or change their defaults in the pipeline, or in the installer's `RLS_*` settings).

**1. No impersonation (default)**

```json
{"rls_source": "none"}
```

**2. Same users for every model, typed in the parameter**

```json
{"rls_source": "list", "rls_scope": "global", "rls_users": "user1@contoso.com,user2@contoso.com"}
```

**3. Same users for every model, from a text file**

```json
{"rls_source": "file", "rls_scope": "global", "rls_users_file": "/lakehouse/default/Files/PerfScenarios/Users/users.txt"}
```

**4. Different users per model, typed inside `models`**

```json
{
  "rls_source": "list",
  "rls_scope": "per_model",
  "models": [
    {"model_key": "SalesA", "dataset": "Sales A", "workspace": "", "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/a.json",
     "users": ["user1@contoso.com", "user2@contoso.com"]},
    {"model_key": "SalesB", "dataset": "Sales B", "workspace": "", "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/b.json",
     "users": ["user3@contoso.com"]}
  ]
}
```

**5. One users file per model**

```json
{
  "rls_source": "file",
  "rls_scope": "per_model",
  "models": [
    {"model_key": "SalesA", "dataset": "Sales A", "workspace": "", "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/a.json",
     "users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_SalesA.txt"},
    {"model_key": "SalesB", "dataset": "Sales B", "workspace": "", "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/b.json",
     "users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_SalesB.txt"}
  ]
}
```

**6. Per-model files with a global file as fallback** (a model without `users_file` uses `rls_users_file`)

```json
{"rls_source": "file", "rls_scope": "per_model", "rls_users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_default.txt"}
```

Switching quickly between two ways of providing users without editing the models:

| From | To | Change |
|---|---|---|
| typed list | file | `rls_source`: `list` → `file`, and fill `rls_users_file` (or `users_file`) |
| global | per model | `rls_scope`: `global` → `per_model`, and fill `users` / `users_file` in each model |
| any | no impersonation | `rls_source`: `none` (the other values are kept but ignored) |

`users` / `users_file` inside `models` are **ignored while `rls_scope = global`**, and the file settings are ignored while `rls_source = list`
(and vice versa), so you can keep all of them in place and only flip the two switches.

## Results

Every run folder (`Files/PerfScenarios/logs/<test>-c<level>-<timestamp>/`) has one CSV per virtual user and a `summary.json` with the
latency percentiles of the successful queries, the failed queries, the lost virtual users and the UTC window. `RunLoadTest_v3` also
returns that summary as its exit value.

| Parameter | Values | What it does |
|---|---|---|
| `stop_on_query_error` | `false` (default), `true` | `false`: a failed query (timeout, throttling, RLS) is a row with `status = error` and the user carries on. `true`: the user stops at its first failed query. Its CSV is written in both cases |
| `fail_on_error_rate` | `1.0` (default), `0` to `1` | The pipeline ends Completed even when queries failed. Set a threshold so `RunLoadTest_v3` fails (after writing `summary.json` and the tables) when the run's error rate is above it. `0` fails on any failed query |
| `write_results_to_tables` | `false` (default), `true` | Also append each run to the Delta tables `loadtest_runs` (one row per run) and `loadtest_queries` (one row per query) of the default lakehouse. Written with `deltalake` to the OneLake path; new columns are merged into existing tables (with an old `deltalake` drop the tables when the schema changes) |

A green run can contain failed queries: read `failed_queries` and `error_rate` in `summary.json` or in the exit value, or use `fail_on_error_rate`.

## Complete example

Two models in parallel, ramp of 6, 20 and 60 users, recorded pace with a 30-second start window, one users file per model:

```json
{
  "models": [
    {"model_key": "SalesA", "dataset": "Sales A", "workspace": "",
     "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/PowerBIPerformanceData_SalesA.json",
     "users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_SalesA.txt"},
    {"model_key": "SalesB", "dataset": "Sales B", "workspace": "Finance",
     "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/PowerBIPerformanceData_SalesB.json",
     "users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_SalesB.txt"}
  ],
  "test_name_prefix": "ramp-v3",
  "ramp_levels": [6, 20, 60],
  "iterations": 1,
  "delay_sec": 4,
  "enable_think_times": true,
  "think_time_scale": 1.0,
  "max_think_time_sec": 60.0,
  "think_time_jitter_pct": 0.1,
  "ramp_up_sec": 30,
  "initial_user_jitter_sec": 2,
  "rls_source": "file",
  "rls_scope": "per_model"
}
```

Here `SalesB` lives in the workspace named `Finance`; `SalesA` is in the workspace where the test runs.

## Where each parameter goes

| Parent (`PL_PerfTest_MultiModel_v3`) | Child (`PL_PerfTest_Ramp_v3`) | Notebook (`RunLoadTest_v3`) |
|---|---|---|
| `models[].model_key` | `model_key` | part of `load_test_name` |
| `models[].dataset` | `dataset` | `dataset` |
| `models[].workspace` | `model_workspace` | `workspace` |
| `models[].queryfile` | `queryfile` | `queryfile` |
| whole `models[]` item | `model_settings` (JSON text) | `model_settings` (`users`, `users_file`) |
| `ramp_levels` | `ramp_levels` (the `ForEach_Ramp` items) | `concurrent_threads` = current level |
| other parameters | same name | same name |

You only fill in the parent. The child pipeline can also be run alone for one model; then `model_key`, `dataset`, `model_workspace` and
`queryfile` are its own parameters.

## Common mistakes

| Symptom | Cause |
|---|---|
| A setting has no effect | The parameter name is misspelled; Fabric ignores unknown names silently. |
| `Navigation file ... not found` | `queryfile` is wrong, has spaces, or the file was not uploaded to the lakehouse. |
| `Authentication failed` / model not found | `dataset` or `workspace` is not the exact display name (a GUID in `workspace` does not work), or the XMLA read endpoint is disabled on the capacity. |
| `Users file not found` / `contains no users` | `rls_source = file` with a wrong path, or a file with only comments. |
| `rls_source = 'file' but no file was given` | `rls_users_file` is empty and the model has no `users_file`. |
| Queries of one virtual user fail with RLS | The impersonated user does not exist or has no read and build permission on that model. |
| `concurrent_threads out of range` | A value of `ramp_levels` is outside 1–300. |
| `summary.json` shows `failed_queries` > 0 | Queries failed during the run; their messages are in the `error` column of the user CSV and in `error.log`. |
