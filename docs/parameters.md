# Parameters

For a field-by-field reference of `PL_PerfTest_MultiModel_v3` (what each parameter expects, the `workspace` format, and how to switch between
lists, files, global users and per-model users) see [pipeline-parameters.md](pipeline-parameters.md).

## Pipeline parameters

Defined in `PL_PerfTest_MultiModel_v3` and forwarded to `PL_PerfTest_Ramp_v3` and then to `RunLoadTest_v3`.
When you schedule or trigger a pipeline, names must match **exactly**; Fabric ignores unknown names without warning.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `models` | Array | one `CHANGE_ME_*` placeholder | List of `{model_key, dataset, workspace, queryfile}` |
| `test_name_prefix` | String | `ramp-v3` | Prefix of run names: `<prefix>-<model_key>-c<N>-<timestamp>` |
| `ramp_levels` | Array | `[1, 5, 10]` | Concurrent users per level, run sequentially per model |
| `iterations` | Int | `1` | Times each user repeats the whole recorded scenario |
| `delay_sec` | Int | `4` | Wait between iterations (and per query when think times are off) |
| `enable_think_times` | Bool | `true` | Replay the pauses between user actions |
| `think_time_scale` | Float | `1.0` | Multiplier for every recorded pause |
| `max_think_time_sec` | Float | `60.0` | Cap on a single scaled pause |
| `think_time_jitter_pct` | Float | `0.1` | Random variation of each pause, 0..1 |
| `fallback_think_time_sec` | Float | `0.0` | Pause between queries if the file has no `User Action` events |
| `ramp_up_sec` | Float | `0.0` | Window over which the users of a level start |
| `initial_user_jitter_sec` | Float | `0.0` | Random extra delay before each user's first action |
| `rls_source` | String | `list` | Where the impersonated identities come from: `list`, `file` or `none` (see *RLS identities*) |
| `rls_scope` | String | `global` | `global`: the same identities for every model; `per_model`: each model uses its own (`users` / `users_file` of its `models` item) |
| `rls_users` | String | empty | Global list: comma-separated UPNs for `EffectiveUserName` |
| `rls_users_file` | String | empty | Global text file with one UPN per line, for example `/lakehouse/default/Files/PerfScenarios/Users/users.txt` |
| `stop_on_query_error` | Bool | `false` | `true`: a virtual user stops at its first failed query, as before 3.4.0 (its rows and CSV are kept). `false`: the failed query is a row with `status = error` and the user continues |
| `fail_on_error_rate` | Float | `1.0` | After writing `summary.json` and the tables, fail the notebook when the run's error rate (0 to 1) is above it. `1.0` never fails, `0` fails on any failed query. Without it a run with failed queries ends Completed |
| `write_results_to_tables` | Bool | `false` | Append each run to the Delta tables `loadtest_runs` and `loadtest_queries` of the default lakehouse |

The notebooks default to think times **off**, which reproduces the original tool; the pipelines default to **on**.

### Fields of each `models` item

| Field | Description |
|---|---|
| `model_key` | Short unique label; letters, digits, `-` and `_`; part of the log folder name |
| `dataset` | Exact name of the semantic model |
| `workspace` | Workspace of the model; empty = the workspace where the test runs |
| `queryfile` | Path in the default lakehouse, starting with `/lakehouse/default/`, no spaces |
| `users` | Optional. List of UPNs (or a comma-separated string) for this model. Used with `rls_source = list` and `rls_scope = per_model` |
| `users_file` | Optional. Text file with the UPNs of this model. Used with `rls_source = file` and `rls_scope = per_model` |

## RLS identities

Row-level security is tested by impersonating users (`EffectiveUserName`). Two switches decide **where the users come from** and
**which models they apply to**, in the same way `enable_think_times` switches the think times:

| `rls_source` | `rls_scope = global` (default) | `rls_scope = per_model` |
|---|---|---|
| `list` (default) | `rls_users` for every model | `users` of the model's item; if the item has none, `rls_users` |
| `file` | `rls_users_file` for every model | `users_file` of the model's item; if the item has none, `rls_users_file` |
| `none` | no impersonation | no impersonation |

- The default (`list`, `global`, empty `rls_users`) means **no impersonation**: the identity that runs the test is used, exactly as before.
- With `per_model`, a model that defines nothing falls back to the global value; the notebook log states which source was used for each run.
- If `rls_source = file` and no file is given, or the file does not exist or has no users, the run fails before any query is sent.
- The identities are spread across the virtual users in turn (`user[i % number_of_users]`). With more virtual users than identities they are reused.
- The log prints how many identities were found and where they come from, **never the UPNs themselves**.

### Users file format

```text
# one user principal name per line
user1@contoso.com
user2@contoso.com   # trailing comments are fine
```

Blank lines and `#` comments are ignored, commas or semicolons also separate users, duplicates are removed ignoring case (the first spelling
is kept), a UTF-8 BOM is accepted, and any other line is rejected with its line number. See [samples/users.example.txt](../samples/users.example.txt).

### Examples

Same users for all models, from a file:

```json
{"rls_source": "file", "rls_scope": "global", "rls_users_file": "/lakehouse/default/Files/PerfScenarios/Users/users.txt"}
```

One file per model (a model without `users_file` uses `rls_users_file` if it is set, otherwise the run fails):

```json
{"rls_source": "file", "rls_scope": "per_model", "models": [
  {"model_key": "SalesA", "dataset": "Sales A", "workspace": "", "queryfile": "...", "users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_SalesA.txt"},
  {"model_key": "SalesB", "dataset": "Sales B", "workspace": "", "queryfile": "...", "users_file": "/lakehouse/default/Files/PerfScenarios/Users/users_SalesB.txt"}
]}
```

Short lists inside `models` (`rls_source = list`, `rls_scope = per_model`): see [samples/models.rls.example.json](../samples/models.rls.example.json).
The item of each model is passed to the notebook as a JSON string (`model_settings`), so keep long lists in a file rather than in `users`.

Users that do not exist or have no read and build permission on the model make the queries of that virtual user fail.

## Think times

A Performance Analyzer export records each **user action** (a click, a slicer change, a page view) and the DAX queries it triggered.
The time between the end of one action's queries and the start of the next action is the **think time** of a real user.

With `enable_think_times = true`, for every action `RunPerfScenario_v3` waits:

```text
applied = min(recorded_pause × think_time_scale, max_think_time_sec) × random(1 − jitter, 1 + jitter)
```

- **One pause per action**, not per query: the queries of one action run back to back, as they do in a report.
- `think_time_scale`: `1.0` recorded pace, `0.5` twice as fast, `2.0` twice as slow, `0` no internal pauses.
- `max_think_time_sec`: avoids a recorded coffee break of five minutes. It is applied before the jitter.
- `think_time_jitter_pct`: `0.1` means each pause varies ±10 %, so users do not move in lockstep. `0` makes runs repeatable.
- `delay_sec` still applies **between iterations**. With think times on, it no longer applies after each query.
- Files without `User Action` events use `fallback_think_time_sec` between queries.

## Ramp and staggered start

Two different things are called ramp:

1. **Ramp of levels** (`ramp_levels`): the pipeline runs 6 users, then 20, then 60, ... one level after another. Each level is a separate run.
2. **Ramp-up inside a level** (`ramp_up_sec`): the users of that level do not all start in the same second.

User *i* of *N* waits `ramp_up_sec × i / N` seconds before starting. For `ramp_up_sec = 60` and 6 users, they start at 0, 10, 20, 30, 40 and 50 s.
`0` starts everybody at once, like the original tool.

`initial_user_jitter_sec` adds a random 0..N s on top of that, per user, so the start times are not on a perfect grid.

## Recommendations

| Goal | Suggestion |
|---|---|
| First run after deploying | Keep `ramp_levels = [1, 5, 10]` and `iterations = 1` |
| Realistic interactive users | `enable_think_times = true`, `think_time_scale = 1`, `think_time_jitter_pct = 0.1`, `ramp_up_sec` ≈ 1/3 of the scenario duration |
| Stress test (maximum pressure) | `enable_think_times = false`, `delay_sec` small, `ramp_up_sec = 0` |
| Repeatable comparison between runs | `think_time_jitter_pct = 0`, `initial_user_jitter_sec = 0` |
| 100 or more users | Raise `%%configure vCores` in `RunLoadTest_v3` (see the first cell of that notebook) |
