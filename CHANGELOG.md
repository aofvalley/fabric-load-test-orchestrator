# Changelog

## 3.4.0

**Behaviour change: a failed query no longer ends the virtual user.** Until 3.3.0 an exception in a query ended that virtual user,
its CSV was never written and the run lost every row of that user. From 3.4.0 the failed query is recorded as a row with
`status = error`, `rows = 0` and the error message (token redacted), a line is added to `error.log`, the connection is reopened if the
error closed it and the user continues with the next query. The CSV is written in `finally`, so partial results always survive.
Set `stop_on_query_error = true` to stop the user at its first failed query as before (its rows and CSV are still kept).

**A green run can contain failed queries.** With the default `stop_on_query_error = false` the notebook and the pipeline end Completed even if queries failed. Read `failed_queries` and `error_rate` in `summary.json` or in the notebook exit value, or set `fail_on_error_rate` so the notebook fails above a threshold.

- **Result schema:** the user CSV files gain two columns, `status` (`ok` or `error`) and `error`. `AnalyzeLoadTest_v3` (queries 1 and 8)
  and `summary.json` count failed queries and compute latency percentiles over successful queries only. Runs without the `status`
  column (3.3.0 and earlier) are read as successful.
- **Run summary:** `RunLoadTest_v3` writes `summary.json` in every run folder and exits with it (`notebookutils.notebook.exit`): latency
  percentiles of the successful queries, failed queries, lost virtual users, error rate, throughput and UTC window. A failed
  `runMultiple` still leaves `summary.json` with the error before the notebook fails.
- New parameter `write_results_to_tables` (notebook and both pipelines, default `false`): appends each run to the Delta tables
  `loadtest_runs` and `loadtest_queries` of the default lakehouse, with explicit schemas. `RunLoadTest_v3` is a Python notebook (no
  Spark), so it writes with `deltalake.write_deltalake` to the OneLake `abfss://` path of the default lakehouse (`/dbo` added on
  schema-enabled lakehouses) with the storage token; the mounted `/lakehouse/default/Tables` path fails on commit. Columns are typed
  (`Int64`, `float64`, `string`) so all-null columns keep their type. The append uses `schema_mode="merge"`, so a table created by an
  earlier version gains the new columns; with an old `deltalake` that does not support it the append is plain and a table with a
  different schema must be dropped first.
- New parameter `stop_on_query_error` (both notebooks and both pipelines, default `false`), see above.
- New parameter `fail_on_error_rate` (`RunLoadTest_v3` and both pipelines, default `1.0`, range 0 to 1): after writing `summary.json`
  and the tables, the notebook fails when the run's error rate is above it. `0` fails on any failed query; `1.0` never fails.
- **ADOMD authentication:** `RunPerfScenario_v3` authenticates like semantic-link (`refresh_tom_access_token` plus an
  `OnAccessTokenExpired` callback). On some capacity and region combinations the `pbi` token passed as `password=` fails with
  "Authentication failed for all authenticators" while sempy works; without sempy the notebook falls back to the previous form. The
  token is no longer part of the logged connection string. `EffectiveUserName` (RLS) keeps working. This relies on a private
  semantic-link module (`sempy.fabric._client._utils`), marked in the code.
- `RunPerfScenario_v3`: the ADOMD `DataReader` is always closed.
- `RunLoadTest_v3`: the polars consolidation accepts CSV files with different columns.

## 3.3.0

- **RLS identities from a text file.** New switches, in the same spirit as `enable_think_times`:
  - `rls_source`: `list` (default), `file` or `none`.
  - `rls_scope`: `global` (default) or `per_model`.
  - `rls_users_file`: global file with one UPN per line (blank lines and `#` comments ignored, duplicates removed, invalid lines rejected with their line number).
  - Each item of `models` may carry `users` or `users_file` for per-model identities; a model without its own falls back to the global value.
  - The defaults reproduce 3.2.0: with the default parameters nothing changes.
- The pipelines pass the item of each model to the notebook as JSON (`model_settings`), so optional keys never break a pipeline expression.
- Installer: validates `users` / `users_file` in `MODELS`, new optional `RLS_SOURCE`, `RLS_SCOPE`, `RLS_USERS`, `RLS_USERS_FILE` defaults,
  creates `Files/PerfScenarios/Users/` and warns when a referenced users file does not exist yet.
- Notebook logs state where the identities come from and how many there are, never the UPNs.
- Samples `users.example.txt` and `models.rls.example.json`; tests for every combination of source and scope.

## 3.2.0

First public release of the repository.

- English notebooks, installer and documentation (Spanish guide in `docs/es/`).
- Repository structure: `notebooks/`, `pipelines/`, `installer/`, `tools/`, `samples/`, `tests/`, `docs/`, `upstream/`.
- `upstream/` holds the untouched original files of `microsoft/fabric-toolbox` (pinned commit, verified by test).
- Pipelines ship with placeholders (`{{WORKSPACE_ID}}`, `{{NOTEBOOK:...}}`, `{{PIPELINE:...}}`) and a safe default ramp `[1, 5, 10]`.
- `RunLoadTest_v3` and `RunPerfScenario_v3`: access token redacted from console output and `error.log`.
- Package manifest no longer carries tenant, user or workspace identifiers; the builder checks for leaks instead of using a deny list.
- Installer verification is generic (foreign ids, ids that do not exist, unresolved placeholders, lakehouse binding, pipeline references).
- Analysis notebook renamed `AnalyzeLoadTest_v3` with English column names.
- Test suite (think-time parser, scenario and load-test notebooks, analysis notebook, installer against a fake Fabric API, package checks) and CI.

## 3.1.x (internal)

Spanish-language builds used while developing the solution: parallel models, sequential ramp, think times, staggered start, RLS
parameter, deployment package and installer.
