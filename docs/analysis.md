# Analyzing the results

`notebooks/AnalyzeLoadTest_v3.ipynb` reads the CSV files that the tests wrote under `Files/PerfScenarios/logs/` with DuckDB.
It does not start tests and does not copy data. Attach, as its default lakehouse, the lakehouse where the tests wrote their results.

Parameters (first code cell): `LOGS`, `RUN_PREFIX` (= `test_name_prefix` of the pipeline, default `ramp-v3`) and
`SINCE_UTC` (ignore earlier runs, for example `"2026-10-28T10:00:00Z"`).

| # | Question it answers | What to look for |
|---|---|---|
| 1 | Which runs exist? | One row per model and level; `users_ok = true` (distinct users = level); `failed_queries` = 0 |
| 2 | Was the ramp sequential? | `OK: sequential`: each level started after the previous level of the same model ended |
| 3 | Real concurrency and start window | `peak_concurrent` close to `users`; `start_window_s` ≈ `ramp_up_sec × (N−1)/N` |
| 4 | Was every query executed? | Same number of queries and actions for every user and iteration |
| 5 | Think times recorded vs applied | `applied_to_original_ratio` ≈ `think_time_scale` (± jitter and cap); one pause per action |
| 6 | **Did the users really wait?** | `avg_actual_pause_s` ≈ `avg_applied_pause_s`; small `avg_deviation_s` |
| 7 | One user, action by action | The scenario as replayed, with applied and measured pauses |
| 8 | Latency per level | Failed queries and error rate; mean, p50, p90, p95 and max duration of the **successful** queries per model and level |
| 9 | Were the models parallel? | `overlap_s > 0` between models |

## Without the notebook: `summary.json`

Every run folder also has a `summary.json` (the exit value of `RunLoadTest_v3`) with the percentiles of the successful queries,
the failed queries and the virtual users that were lost. See [architecture.md](architecture.md#run-summary-and-exit-value).
With `write_results_to_tables = true` the same data is in the Delta tables `loadtest_runs` and `loadtest_queries`.

## Failed queries

A query that fails (timeout, throttling, RLS error...) is recorded as a row with `status = error` and its message in `error`;
the virtual user goes on with the next query. Queries 1 and 8 count them and query 8 leaves them out of the percentiles.
A growing `error_rate` with the level is a capacity or model limit, as important as the latency. Runs written before 3.4.0 have
no `status` column and are read as all successful.

## Reading query 8 (latency per level)

`p50` is the typical query, `p90` and `p95` the slow tail, `max` the worst case. When the level grows:

- a flat p50 and p90 means the model absorbs the load;
- p50 stable but p90/p95/max growing means some queries start to queue (usually the heaviest ones);
- everything growing means saturation of the capacity or the model.

Compare levels of the **same model**; models of different size are not comparable with each other.
Latency also includes time queued while the capacity is throttled: check the capacity metrics app if the tail grows suddenly.

## Do the results prove natural user behaviour?

Query 6 proves that the replayed pauses happened. Query 3 and 5 prove that users were spread in time. Together with a flat or slowly growing
latency curve in query 8 they show that the ramp reproduces an interactive load rather than a burst of simultaneous queries.
A burst (all users, no pauses) gives a much higher `peak_concurrent` for the same number of users, which is what a stress test measures.
