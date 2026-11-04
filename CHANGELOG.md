# Changelog

## 3.4.0

- `RunLoadTest_v3` writes `summary.json` in every run folder and exits with it (`notebookutils.notebook.exit`): latency
  percentiles of the successful queries, failed queries, lost virtual users, error rate, throughput and UTC window. A failed
  `runMultiple` still leaves `summary.json` with the error before the notebook fails.
- New parameter `write_results_to_tables` (notebook and both pipelines, default `false`): appends each run to the Delta tables
  `loadtest_runs` and `loadtest_queries` of the default lakehouse, with explicit schemas.

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
