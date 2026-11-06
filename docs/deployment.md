# Deployment

The installer notebook deploys the notebooks and pipelines into the workspace **where it runs**. It computes every reference
(workspace, lakehouse, notebook and pipeline ids) in that workspace, so nothing from the machine that built the package is carried over.

## Requirements

- Fabric workspace on a capacity; Contributor role or higher.
- A **lakehouse in the same workspace**.
- XMLA read endpoint enabled on the capacity (tenant requirement for querying semantic models).
- The identity that runs the tests needs **read and build** permission on every semantic model tested.

## Steps

1. **Obtain the package**: download `FabricLoadTest_v3_package.zip` and `Setup_LoadTest_v3.ipynb` from the Releases page, or run
   `python tools/build_package.py` (output: `dist/FabricLoadTest_v3_package.zip`).
2. **Import** `Setup_LoadTest_v3.ipynb` into the workspace (*Import → Notebook*).
3. Attach the lakehouse as the notebook's **default** lakehouse (Explorer → *Add data items*).
4. **Upload** the zip to `Files/deploy/` of that lakehouse (or change `PACKAGE_PATH`).
5. Edit the **Parameters** cell:
   - `MODELS`: list of models (see [samples/models.example.json](../samples/models.example.json)) or `None` to set them later. Each model may
     carry `users` or `users_file` (per-model RLS identities).
   - `RLS_SOURCE`, `RLS_SCOPE`, `RLS_USERS`, `RLS_USERS_FILE` (optional): defaults written into both pipelines. `None` keeps the pipeline
     default (`list`, `global`, no users). The installer warns if a referenced users file does not exist yet; upload it to
     `Files/PerfScenarios/Users/` before running. See [RLS identities](parameters.md#rls-identities).
   - `OVERWRITE`: `True` updates items that already exist with the same name; `False` aborts if any exists.
   - `DRY_RUN`: start with `True`; the notebook prints the plan and changes nothing.
6. **Run all**. With `DRY_RUN = False` the installer creates or updates the items, creates `Files/PerfScenarios/Queries`,
   `Files/PerfScenarios/Users` and `Files/PerfScenarios/logs`, and verifies the result.
7. Upload one Performance Analyzer JSON per model to `Files/PerfScenarios/Queries/` (and the users files to `Files/PerfScenarios/Users/` if you use RLS) and open `PL_PerfTest_MultiModel_v3`.

## What the verification checks

- The zip content matches the SHA-256 hashes of `manifest.json`.
- Every GUID inside the deployed items is this workspace, this lakehouse or an item deployed by this run
  (otherwise: *ids that do not belong to this workspace*).
- Every referenced item exists in the workspace.
- No `{{placeholder}}` is left.
- Notebooks are bound to this lakehouse.
- `PL_PerfTest_Ramp_v3` calls the `RunLoadTest_v3` of this workspace and `PL_PerfTest_MultiModel_v3` calls the `PL_PerfTest_Ramp_v3` of this workspace.

Names are never used as evidence of a leftover: a workspace or lakehouse may legitimately have any name.

## Troubleshooting

| Message | Cause and fix |
|---|---|
| `This notebook has no default lakehouse` | Attach a lakehouse to the installer notebook. |
| `The default lakehouse is in another workspace` | Use a lakehouse of the same workspace. |
| `Package not found` | Upload the zip to the lakehouse or fix `PACKAGE_PATH` (relative to the lakehouse root). |
| `SHA-256 mismatch` | The zip is damaged or was modified; download or build it again. |
| `already exists and OVERWRITE = False` | Set `OVERWRITE = True` or rename the existing items. |
| `MODELS[n]: ...` | A model entry is invalid (also `users` / `users_file`); the installer fails before creating anything. |
| `RLS_SOURCE = 'file' needs RLS_USERS_FILE` | Give the global file, or use `RLS_SCOPE = 'per_model'` with a `users_file` in every model. |
| `WARNING: users file not found yet` | Upload the file to `Files/PerfScenarios/Users/` before running with `rls_source = 'file'`. |
| `ItemDisplayNameNotAvailableYet` | A just-deleted item still reserves its name; wait a few minutes and run again. |
| HTTP 403 | The identity is not Contributor in the workspace. |
| Pipeline error `WorkspaceNotFound` | The pipeline still holds an id of another workspace: it was imported manually. Use the installer instead. |

## Updating or removing

Run the installer again with `OVERWRITE = True` to update in place; ids stay the same, so schedules keep working.
To remove the solution, delete the five items in the workspace UI. Result files under `Files/PerfScenarios/logs/` are kept until you delete them.
