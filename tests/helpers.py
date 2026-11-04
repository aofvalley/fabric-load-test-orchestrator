"""Shared helpers for the tests: notebook loading, a fake Fabric/ADOMD runtime and a runner for the scenario notebook."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
UPSTREAM = ROOT / "upstream"
SAMPLE = ROOT / "samples" / "sample_performance_data.json"
SECRET_TOKEN = "SECRET-TOKEN-abc123"

sys.path.insert(0, str(ROOT / "tools"))


def load_notebook(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def code_cells(nb: dict) -> list[str]:
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def find_cell(nb: dict, needle: str) -> str:
    """The only code cell whose source contains ``needle``."""
    hits = [s for s in code_cells(nb) if needle in s]
    assert len(hits) == 1, f"expected exactly one code cell containing {needle!r}, found {len(hits)}"
    return hits[0]


def parameters_cell(nb: dict) -> str:
    hits = [c for c in nb["cells"] if c["cell_type"] == "code" and "parameters" in c["metadata"].get("tags", [])]
    assert len(hits) == 1, "a notebook must have exactly one cell tagged 'parameters'"
    return "".join(hits[0]["source"])


# ------------------------------------------------------------------------------------------ fake runtime
class _Reader:
    def Read(self):  # noqa: N802 (ADOMD naming)
        return False

    def Close(self):  # noqa: N802
        pass


class _Command:
    CommandText = ""

    def ExecuteReader(self):  # noqa: N802
        time.sleep(0.002)  # tiny artificial latency so that durations are not zero
        return _Reader()


class FakeAdomdConnection:
    def __init__(self, connection_string):
        self.connection_string = connection_string

    def Open(self):  # noqa: N802
        pass

    def CreateCommand(self):  # noqa: N802
        return _Command()

    def Close(self):  # noqa: N802
        pass


def install_fake_fabric_modules(monkeypatch) -> None:
    """Replace sempy and the ADOMD client, which only exist inside Fabric, with small fakes."""
    sempy = types.ModuleType("sempy")
    fabric = types.ModuleType("sempy.fabric")
    fabric.create_tom_server = lambda: None
    fabric.get_lakehouse_id = lambda: "lakehouse-id"
    fabric.get_workspace_id = lambda: "workspace-id"
    sempy.fabric = fabric
    microsoft = types.ModuleType("Microsoft")
    analysis = types.ModuleType("Microsoft.AnalysisServices")
    adomd = types.ModuleType("Microsoft.AnalysisServices.AdomdClient")
    adomd.AdomdConnection = FakeAdomdConnection
    for name, module in {"sempy": sempy, "sempy.fabric": fabric, "Microsoft": microsoft,
                         "Microsoft.AnalysisServices": analysis, "Microsoft.AnalysisServices.AdomdClient": adomd}.items():
        monkeypatch.setitem(sys.modules, name, module)


def make_notebookutils(root: Path, workspace_name: str = "test-workspace", runmultiple=None):
    class FS:
        @staticmethod
        def mkdirs(path):
            os.makedirs(path, exist_ok=True)

    notebook = types.SimpleNamespace(runMultiple=runmultiple) if runmultiple else types.SimpleNamespace()
    return types.SimpleNamespace(
        credentials=types.SimpleNamespace(getToken=lambda audience: SECRET_TOKEN),
        fs=FS,
        notebook=notebook,
        runtime=types.SimpleNamespace(context={"currentWorkspaceName": workspace_name}),
    )


def lakehouse_path(source: str, root: Path) -> str:
    """Point the notebook's default-lakehouse paths at a temporary folder."""
    return source.replace("/lakehouse/default", root.as_posix())


def run_scenario_user(root: Path, quiet: bool = True, **injected) -> str:
    """Run the four code cells of RunPerfScenario_v3 for one virtual user. Returns what the notebook printed.

    ``injected`` plays the role of the cell Fabric injects below the Parameters cell when a pipeline passes parameters.
    """
    cells = [lakehouse_path(s, root) for s in code_cells(load_notebook(NOTEBOOKS / "RunPerfScenario_v3.ipynb"))]
    assert len(cells) == 4
    printed: list[str] = []
    namespace = {"notebookutils": make_notebookutils(root)}
    if quiet:  # redirect_stdout is process-wide, so threads use a private print instead
        namespace["print"] = lambda *a, **k: printed.append(" ".join(str(x) for x in a))
    exec(compile(cells[0], "parameters", "exec"), namespace)
    exec(compile("\n".join(f"{k} = {v!r}" for k, v in injected.items()), "injected", "exec"), namespace)
    for index, source in enumerate(cells[1:], start=2):
        exec(compile(source, f"scenario-cell-{index}", "exec"), namespace)
    return "\n".join(printed)


def capture_stdout(function, *args, **kwargs) -> tuple[object, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = function(*args, **kwargs)
    return result, buffer.getvalue()
