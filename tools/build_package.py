#!/usr/bin/env python3
"""Build the deployment package ``dist/FabricLoadTest_v3_package.zip`` from the files of this repository.

The package contains the notebooks, the pipeline templates, the installer notebook and a ``manifest.json`` with the SHA-256 of
every file. Before writing the zip the script checks that nothing environment-specific leaked into it (workspace or item ids,
real e-mail addresses, tenant names, saved outputs, personal notebook metadata).

Usage::

    python tools/build_package.py                       # writes dist/FabricLoadTest_v3_package.zip
    python tools/build_package.py --deny-file my.txt    # extra strings that must not appear (one per line, kept out of the repo)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "FabricLoadTest_v3"
VERSION = "3.4.0"

GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
EMAIL = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+[A-Za-z]{2,})")
ALLOWED_EMAIL_DOMAINS = {"contoso.com", "example.com", "domain.com"}  # placeholders used in documentation and examples

# Order matters: the installer deploys the items in this order (the parent pipeline needs the id of the child pipeline).
ITEMS = [
    ("Notebook", "RunPerfScenario_v3", "notebooks/RunPerfScenario_v3.ipynb",
     "Per-virtual-user scenario: replays the queries of the JSON file with think times, staggered start and pause logging."),
    ("Notebook", "RunLoadTest_v3", "notebooks/RunLoadTest_v3.ipynb",
     "One semantic model at one concurrency level. Receives its parameters from the pipeline and calls RunPerfScenario_v3."),
    ("Notebook", "AnalyzeLoadTest_v3", "notebooks/AnalyzeLoadTest_v3.ipynb",
     "Read-only analysis (DuckDB over the result CSV files): ramp, think times and parallel models."),
    ("DataPipeline", "PL_PerfTest_Ramp_v3", "pipelines/PL_PerfTest_Ramp_v3.json",
     "One semantic model: ramp of concurrent users (sequential ForEach) over RunLoadTest_v3."),
    ("DataPipeline", "PL_PerfTest_MultiModel_v3", "pipelines/PL_PerfTest_MultiModel_v3.json",
     "Parallel ForEach (at most 10 models) over the models parameter; each model runs PL_PerfTest_Ramp_v3."),
]
INSTALLER = "installer/Setup_LoadTest_v3.ipynb"
TOKENS = {
    "PL_PerfTest_Ramp_v3": ["{{WORKSPACE_ID}}", "{{NOTEBOOK:RunLoadTest_v3}}"],
    "PL_PerfTest_MultiModel_v3": ["{{PIPELINE:PL_PerfTest_Ramp_v3}}"],
}
FOLDERS = ["Files/PerfScenarios/Queries", "Files/PerfScenarios/Users", "Files/PerfScenarios/logs"]


def _notebook_scan_text(raw: bytes) -> str:
    """Text of a notebook that can carry references: cell sources and metadata (cell ids are not references)."""
    nb = json.loads(raw)
    parts = [json.dumps(nb.get("metadata", {}), ensure_ascii=False)]
    for cell in nb.get("cells", []):
        parts.append("".join(cell.get("source", [])))
        parts.append(json.dumps(cell.get("metadata", {}), ensure_ascii=False))
    return "\n".join(parts)


def find_problems(files: dict[str, bytes], deny: list[str] | None = None) -> list[str]:
    """Return a list of human-readable problems; an empty list means the package is clean."""
    problems: list[str] = []
    for path, raw in files.items():
        if path == "manifest.json":
            continue
        if path.endswith(".ipynb"):
            nb = json.loads(raw)
            text = _notebook_scan_text(raw)
            if "dependencies" in nb.get("metadata", {}) and not path.startswith("installer/"):
                problems.append(f"{path}: contains a lakehouse binding (metadata.dependencies); the installer adds it")
            for i, cell in enumerate(nb.get("cells", []), 1):
                if cell["cell_type"] == "code" and (cell.get("outputs") or cell.get("execution_count") is not None):
                    problems.append(f"{path}: cell {i} has saved outputs or an execution count")
                if "cellStatus" in cell.get("metadata", {}):
                    problems.append(f"{path}: cell {i} carries run metadata (cellStatus)")
        else:
            text = raw.decode("utf-8")
        for g in sorted(set(GUID.findall(text))):
            problems.append(f"{path}: contains a GUID ({g}); ids must be computed by the installer")
        for m in EMAIL.finditer(text):
            if m.group(1).lower() not in ALLOWED_EMAIL_DOMAINS:
                problems.append(f"{path}: contains an e-mail address ({m.group(0)})")
        if re.search(r"onmicrosoft\.com", text, re.I):
            problems.append(f"{path}: mentions an onmicrosoft.com tenant")
        for s in deny or []:
            if s and s.lower() in text.lower():
                problems.append(f"{path}: contains a denied string ({s!r})")
    return problems


def collect_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for _, _, rel, _ in ITEMS:
        files[rel] = (ROOT / rel).read_bytes()
    files[INSTALLER] = (ROOT / INSTALLER).read_bytes()
    return files


def build_manifest(files: dict[str, bytes]) -> dict:
    return {
        "package": PACKAGE,
        "version": VERSION,
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": [
            {"type": kind, "name": name, "file": rel, "description": description, "tokens": TOKENS.get(name, []),
             "sha256": hashlib.sha256(files[rel]).hexdigest()}
            for kind, name, rel, description in ITEMS
        ],
        "folders": FOLDERS,
    }


def build(output_dir: Path, deny: list[str] | None = None) -> Path:
    files = collect_files()
    problems = find_problems(files, deny)
    if problems:
        raise SystemExit("The package contains environment-specific content:\n  - " + "\n  - ".join(problems))
    manifest = build_manifest(files)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{PACKAGE}_package.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for rel, raw in files.items():
            z.writestr(rel, raw)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="output folder (default: dist/)")
    parser.add_argument("--deny-file", type=Path, help="file with extra strings that must not appear in the package, one per line")
    args = parser.parse_args(argv)
    deny = [l.strip() for l in args.deny_file.read_text(encoding="utf-8").splitlines() if l.strip()] if args.deny_file else []
    target = build(args.output, deny)
    print(f"{target} ({target.stat().st_size / 1024:.0f} KB), version {VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
