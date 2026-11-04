# Parameters

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
| `rls_users` | String | empty | Comma-separated UPNs for `EffectiveUserName` |

The notebooks default to think times **off**, which reproduces the original tool; the pipelines default to **on**.

### Fields of each `models` item

| Field | Description |
|---|---|
| `model_key` | Short unique label; letters, digits, `-` and `_`; part of the log folder name |
| `dataset` | Exact name of the semantic model |
| `workspace` | Workspace of the model; empty = the workspace where the test runs |
| `queryfile` | Path in the default lakehouse, starting with `/lakehouse/default/`, no spaces |

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
