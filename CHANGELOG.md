# Changelog

## Unreleased

- New `promotion-gate/`: a promotion gate for semantic models built on this orchestrator. Best Practice Analyzer and
  VertiPaq, a full load test with `PL_PerfTest_MultiModel_v3`, a load test report with prioritised improvements and the
  Fabric Capacity Metrics of the test window end in a PASS, WARN or FAIL certificate. It ships a Fabric App (Rayfin) to
  pick the model, launch and follow the gate and sign the promotion with a deployment pipeline, the `smgate` CLI, CI
  templates, a Copilot CLI and Claude Code plugin, a one-command deployment (`promotion-gate/deploy/deploy.ps1`) and a
  success case that passes the gate. Documentation in Spanish: [promotion-gate/README.md](promotion-gate/README.md).

## 3.3.0

- `RunLoadTest_v3` writes `summary.json` in every run folder and exits with it (`notebookutils.notebook.exit`): latency
  percentiles of the successful queries, failed queries, lost virtual users, error rate, throughput and UTC window. A failed
  `runMultiple` still leaves `summary.json` with the error before the notebook fails.
- New parameter `write_results_to_tables` (notebook and both pipelines, default `false`): appends each run to the Delta tables
  `loadtest_runs` and `loadtest_queries` of the default lakehouse, with explicit schemas.
- `RunPerfScenario_v3`: a failed query no longer ends the virtual user. It is recorded as a row with `status = error`, `rows = 0`
  and the error message (token redacted), a line is added to `error.log`, the connection is reopened if it was closed and
  the user continues. New CSV columns `status` and `error`. The CSV is written in `finally`, so partial results survive.
  The ADOMD `DataReader` is always closed.
- `AnalyzeLoadTest_v3`: queries 1 and 8 count failed queries; query 8 computes the percentiles over successful queries.
  Runs without the `status` column are read as successful.
- `RunLoadTest_v3`: the polars consolidation accepts CSV files with different columns.
- `RunPerfScenario_v3`: ADOMD connections authenticate like semantic-link (`refresh_tom_access_token` plus an
  `OnAccessTokenExpired` callback). Some tenants reject the token passed as `password=` with "Authentication failed for all
  authenticators"; without sempy the notebook falls back to the previous form. The token is no longer part of the logged
  connection string.

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
