# Notice and attribution

This repository is an **independent, community extension** of **FabricLoadTestTool**, which is part of
[`microsoft/fabric-toolbox`](https://github.com/microsoft/fabric-toolbox/tree/main/tools/FabricLoadTestTool)
(MIT License, Copyright (c) Microsoft Corporation).

It is **not** an official Microsoft project and is not endorsed or supported by Microsoft.

## What comes from the original

The folder [`upstream/`](upstream) contains the original files, copied **byte for byte** from the commit
`5012e9b76c478b7dba4d7b2dc58248fbf38e4b45` of `microsoft/fabric-toolbox`:

| File | Git blob SHA-1 (as published by GitHub) |
|---|---|
| `upstream/RunLoadTest.ipynb` | `1820b9a09ccc7ed9d7df727efa1e5914c3dd1747` |
| `upstream/RunPerfScenario.ipynb` | `bb63ac1daaa6cb7707730827c5245338c713ae0e` |
| `upstream/readme.md` | `f6f95f062215f2d636186f23dcfd5572b7df3e48` |

A unit test (`tests/test_package.py`) fails if any of these files is modified.

## What is derived from the original

`notebooks/RunLoadTest_v3.ipynb` and `notebooks/RunPerfScenario_v3.ipynb` are derived from the two original notebooks.
The original structure, the use of `notebookutils.notebook.runMultiple`, the XMLA/ADOMD connection and the CSV result format
are kept. The changes are listed in [docs/changes-from-upstream.md](docs/changes-from-upstream.md).

Everything else (pipelines, installer, analysis notebook, tests, tooling and documentation) is new.

## License

MIT, see [LICENSE](LICENSE). The original copyright notice is kept as required by the MIT License.
