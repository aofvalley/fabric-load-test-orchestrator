"""Notebooks del gate: se escriben como .py con celdas `# %%` (legibles en el diff) y se convierten a ipynb al desplegar."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .fabric_api import b64

CELL = re.compile(r"^# %%(?P<rest>.*)$")


def py_to_ipynb(source: str) -> dict[str, Any]:
    """`# %% [markdown]` crea una celda markdown (líneas con '# '), `# %% [parameters]` la celda de parámetros."""
    cells: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in source.splitlines():
        m = CELL.match(line)
        if m:
            rest = m.group("rest")
            kind = "markdown" if "[markdown]" in rest else "code"
            current = {"cell_type": kind, "metadata": {}, "source": []}
            if "[parameters]" in rest:
                current["metadata"]["tags"] = ["parameters"]
            if kind == "code":
                current["outputs"], current["execution_count"] = [], None
            cells.append(current)
            continue
        if current is None:
            continue
        if current["cell_type"] == "markdown":
            line = line[2:] if line.startswith("# ") else line.lstrip("#")
        current["source"].append(line + "\n")
    for c in cells:
        while c["source"] and not c["source"][-1].strip():
            c["source"].pop()
        if c["source"]:
            c["source"][-1] = c["source"][-1].rstrip("\n")
    return {
        "nbformat": 4, "nbformat_minor": 5, "cells": cells,
        "metadata": {"language_info": {"name": "python"},
                     "kernel_info": {"name": "synapse_pyspark"},
                     "microsoft": {"language": "python", "language_group": "synapse_pyspark"}},
    }


def bind_lakehouse(nb: dict[str, Any], workspace_id: str, lakehouse_id: str, lakehouse_name: str) -> dict[str, Any]:
    nb.setdefault("metadata", {})["dependencies"] = {"lakehouse": {
        "known_lakehouses": [{"id": lakehouse_id}], "default_lakehouse": lakehouse_id,
        "default_lakehouse_name": lakehouse_name, "default_lakehouse_workspace_id": workspace_id}}
    return nb


def notebook_definition(nb: dict[str, Any]) -> dict[str, Any]:
    return {"format": "ipynb", "parts": [{"path": "notebook-content.ipynb",
                                          "payload": b64(json.dumps(nb, ensure_ascii=False)),
                                          "payloadType": "InlineBase64"}]}


def parameters_of(nb: dict[str, Any]) -> dict[str, str]:
    """Nombres y valores por defecto (texto) de la celda de parámetros."""
    cell = next((c for c in nb["cells"] if "parameters" in c.get("metadata", {}).get("tags", [])), None)
    out = {}
    for line in "".join(cell["source"]).splitlines() if cell else []:
        m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.+?)\s*(#.*)?$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def load_notebooks(folder: str | Path) -> dict[str, dict[str, Any]]:
    return {p.stem: py_to_ipynb(p.read_text(encoding="utf-8")) for p in sorted(Path(folder).glob("NB_*.py"))}
