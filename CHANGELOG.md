# Changelog

## 3.3.0

- `RunLoadTest_v3` writes `summary.json` in every run folder and exits with it (`notebookutils.notebook.exit`): latency
  percentiles of the successful queries, failed queries, lost virtual users, error rate, throughput and UTC window. A failed
  `runMultiple` still leaves `summary.json` with the error before the notebook fails.
- New parameter `write_results_to_tables` (notebook and both pipelines, default `false`): appends each run to the Delta tables
  `loadtest_runs` and `loadtest_queries` of the default lakehouse, with explicit schemas.

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
