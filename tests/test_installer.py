"""Tests of Setup_LoadTest_v3: the installer notebook is run cell by cell against an in-memory fake of the Fabric REST API."""
import base64
import hashlib
import json
import re
import time
import uuid
import zipfile
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")

import build_package as bp
from helpers import ROOT, code_cells, load_notebook

INSTALLER = ROOT / "installer" / "Setup_LoadTest_v3.ipynb"
WS_ID = "11111111-2222-3333-4444-555555555555"
LH_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_WS = "99999999-8888-7777-6666-555555555555"


class Response:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = "" if body is None else json.dumps(body)

    def json(self):
        return self._body


class FakeFabric:
    """Just enough of the Fabric REST API for the installer: items CRUD, definitions and long-running operations."""

    def __init__(self, ws=WS_ID, lro=True):
        self.ws, self.lro = ws, lro
        self.items = {}        # id -> {"id", "type", "displayName", "description", "definition"}
        self.operations = {}   # op id -> result body
        self.calls = []

    def add(self, kind, name, definition=None):
        item = {"id": str(uuid.uuid4()), "type": kind, "displayName": name, "description": "", "definition": definition}
        self.items[item["id"]] = item
        return item

    def by_name(self, name):
        return next(i for i in self.items.values() if i["displayName"] == name)

    def _accepted(self, result):
        op = str(uuid.uuid4())
        self.operations[op] = result
        return Response(202, None, {"x-ms-operation-id": op, "Retry-After": "1"})

    def request(self, method, url, headers=None, data=None, timeout=None):
        assert headers["Authorization"].startswith("Bearer "), "every call must carry the token"
        path = url.split("/v1/", 1)[1]
        body = json.loads(data) if data else None
        self.calls.append((method, path))
        if method == "GET" and path == f"workspaces/{self.ws}":
            return Response(200, {"id": self.ws})
        if method == "GET" and path.startswith(f"workspaces/{self.ws}/items"):
            kind = re.search(r"type=(\w+)", path)
            value = [{k: i[k] for k in ("id", "type", "displayName")} for i in self.items.values()
                     if not kind or i["type"] == kind.group(1)]
            return Response(200, {"value": value})
        if method == "POST" and path == f"workspaces/{self.ws}/items":
            if any(i["displayName"] == body["displayName"] and i["type"] == body["type"] for i in self.items.values()):
                return Response(409, {"errorCode": "ItemDisplayNameAlreadyInUse"})
            item = self.add(body["type"], body["displayName"], body["definition"])
            item["description"] = body.get("description", "")
            result = {"id": item["id"], "displayName": item["displayName"]}
            return self._accepted(result) if self.lro and item["type"] == "Notebook" else Response(201, result)
        match = re.fullmatch(rf"workspaces/{self.ws}/items/([\w-]+)/(updateDefinition|getDefinition)(\?format=ipynb)?", path)
        if match and method == "POST":
            item = self.items[match.group(1)]
            if match.group(2) == "updateDefinition":
                item["definition"] = body["definition"]
                return Response(200, None)
            return Response(200, {"definition": {"parts": item["definition"]["parts"]}})
        match = re.fullmatch(rf"workspaces/{self.ws}/items/([\w-]+)", path)
        if match and method == "PATCH":
            self.items[match.group(1)].update(body)
            return Response(200, {})
        return Response(404, {"errorCode": "NotFound", "path": path})

    def get(self, url, headers=None, timeout=None):
        path = url.split("/v1/", 1)[1]
        match = re.fullmatch(r"operations/([\w-]+)(/result)?", path)
        if not match or match.group(1) not in self.operations:
            return Response(404, {})
        if match.group(2):
            return Response(200, self.operations[match.group(1)])
        return Response(200, {"status": "Succeeded"})

    def definition_text(self, name):
        part = self.by_name(name)["definition"]["parts"][0]
        return base64.b64decode(part["payload"]).decode("utf-8")


class Lakehouse:
    def __init__(self, root: Path):
        self.root = root

    def local(self, path: str) -> Path:
        return self.root / path.replace("/lakehouse/default/", "", 1).lstrip("/")


def make_zip(path: Path, mutate=None, manifest_hashes_from_mutated=False):
    """Package like tools/build_package.py does, optionally changing a file (to simulate leftovers or tampering)."""
    files = bp.collect_files()
    manifest = bp.build_manifest(files)
    if mutate:
        for rel, transform in mutate.items():
            files[rel] = transform(files[rel])
        if manifest_hashes_from_mutated:
            manifest = bp.build_manifest(files)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for rel, raw in files.items():
            z.writestr(rel, raw)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = FakeFabric()
    lake = Lakehouse(tmp_path / "lakehouse")
    make_zip(lake.root / "Files" / "deploy" / "FabricLoadTest_v3_package.zip")
    monkeypatch.setattr(requests, "request", fake.request)
    monkeypatch.setattr(requests, "get", fake.get)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return fake, lake


def run_installer(fake, lake, ws_name="Perf Workspace", lh_name="PerfLakehouse", lh_id=LH_ID, lh_ws=WS_ID, **parameters):
    """Run the installer cells; ``parameters`` plays the role of the values a user types in the Parameters cell."""
    printed = []

    class FS:
        def mkdirs(self, path):
            lake.local(path).mkdir(parents=True, exist_ok=True)

    class Credentials:
        def getToken(self, audience):
            return "fake-token"

    class Runtime:
        context = {"currentWorkspaceId": WS_ID, "currentWorkspaceName": ws_name, "defaultLakehouseId": lh_id,
                   "defaultLakehouseName": lh_name, "defaultLakehouseWorkspaceId": lh_ws}

    notebookutils = type("NotebookUtils", (), {"runtime": Runtime, "credentials": Credentials(), "fs": FS()})
    cells = code_cells(load_notebook(INSTALLER))
    assert len(cells) == 6

    def local_paths(source):  # the only three places that read or write the lakehouse by its /lakehouse/default path
        for old, new in (('"/lakehouse/default/" + PACKAGE_PATH', 'LAKEHOUSE_ROOT + "/" + PACKAGE_PATH'),
                         ('queries_dir = "/lakehouse/default/Files/PerfScenarios/Queries"',
                          'queries_dir = LAKEHOUSE_ROOT + "/Files/PerfScenarios/Queries"')):
            source = source.replace(old, new)
        return source

    namespace = {"notebookutils": notebookutils, "LAKEHOUSE_ROOT": lake.root.as_posix(),
                 "print": lambda *a, **k: printed.append(" ".join(str(x) for x in a))}
    sources = [local_paths(c) for c in cells]
    assert "LAKEHOUSE_ROOT" in sources[1] and "LAKEHOUSE_ROOT" in sources[5]
    exec(compile(sources[0], "parameters", "exec"), namespace)
    exec(compile("\n".join(f"{k} = {v!r}" for k, v in parameters.items()), "injected", "exec"), namespace)
    for index, source in enumerate(sources[1:], start=2):
        exec(compile(source, f"installer-cell-{index}", "exec"), namespace)
    return namespace, "\n".join(printed)


def test_dry_run_shows_the_plan_and_changes_nothing(env):
    fake, lake = env
    _, out = run_installer(fake, lake, DRY_RUN=True)
    assert out.count("create ") >= 5 and "DRY RUN: nothing was created" in out and "verification skipped" in out
    assert fake.items == {}
    assert not (lake.root / "Files" / "PerfScenarios").exists()
    assert not any(m != "GET" and not p.endswith("/getDefinition") for m, p in fake.calls)


def test_deploy_creates_every_item_with_references_of_this_workspace(env):
    fake, lake = env
    namespace, out = run_installer(fake, lake)
    assert "VERIFICATION OK" in out
    names = {i["displayName"]: i for i in fake.items.values()}
    assert set(names) == {"RunPerfScenario_v3", "RunLoadTest_v3", "AnalyzeLoadTest_v3", "PL_PerfTest_Ramp_v3", "PL_PerfTest_MultiModel_v3"}
    ramp = json.loads(fake.definition_text("PL_PerfTest_Ramp_v3"))
    notebook_activity = ramp["properties"]["activities"][0]["typeProperties"]["activities"][0]["typeProperties"]
    assert notebook_activity["workspaceId"] == WS_ID and notebook_activity["notebookId"] == names["RunLoadTest_v3"]["id"]
    multi = json.loads(fake.definition_text("PL_PerfTest_MultiModel_v3"))
    reference = multi["properties"]["activities"][0]["typeProperties"]["activities"][0]["typeProperties"]["pipeline"]["referenceName"]
    assert reference == names["PL_PerfTest_Ramp_v3"]["id"]
    for name in ("RunPerfScenario_v3", "RunLoadTest_v3", "AnalyzeLoadTest_v3"):
        dependencies = json.loads(fake.definition_text(name))["metadata"]["dependencies"]["lakehouse"]
        assert dependencies["default_lakehouse"] == LH_ID and dependencies["default_lakehouse_workspace_id"] == WS_ID
    for item in fake.items.values():
        assert "{{" not in fake.definition_text(item["displayName"])
    assert (lake.root / "Files" / "PerfScenarios" / "Queries").is_dir() and (lake.root / "Files" / "PerfScenarios" / "logs").is_dir()
    assert "WARNING: the `models` parameter" in out


def test_deploy_works_when_the_api_answers_synchronously(env):
    fake, lake = env
    fake.lro = False
    _, out = run_installer(fake, lake)
    assert "VERIFICATION OK" in out and len(fake.items) == 5


def test_rerun_updates_the_existing_items_without_duplicating_them(env):
    fake, lake = env
    run_installer(fake, lake)
    ids = {i["displayName"]: i["id"] for i in fake.items.values()}
    _, out = run_installer(fake, lake)
    assert "update" in out and "VERIFICATION OK" in out
    assert {i["displayName"]: i["id"] for i in fake.items.values()} == ids


def test_overwrite_false_aborts_before_touching_anything(env):
    fake, lake = env
    run_installer(fake, lake)
    before = {i["id"]: json.dumps(i["definition"]) for i in fake.items.values()}
    calls = len(fake.calls)
    with pytest.raises(RuntimeError, match="already exists and OVERWRITE = False"):
        run_installer(fake, lake, OVERWRITE=False)
    assert before == {i["id"]: json.dumps(i["definition"]) for i in fake.items.values()}
    assert not any(m in ("POST", "PATCH") for m, _ in fake.calls[calls:] if not _.endswith("getDefinition"))


def test_valid_models_are_written_into_the_parent_pipeline(env):
    fake, lake = env
    models = [{"model_key": " SalesA ", "dataset": "Sales A", "workspace": None,
               "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/a.json"},
              {"model_key": "SalesB", "dataset": "Sales B", "workspace": "Other", "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/b.json"}]
    _, out = run_installer(fake, lake, MODELS=models)
    stored = json.loads(fake.definition_text("PL_PerfTest_MultiModel_v3"))["properties"]["parameters"]["models"]["defaultValue"]
    assert [m["model_key"] for m in stored] == ["SalesA", "SalesB"] and stored[0]["workspace"] == "" and stored[1]["workspace"] == "Other"
    assert "WARNING: the `models` parameter" not in out
    ramp = json.loads(fake.definition_text("PL_PerfTest_Ramp_v3"))
    assert ramp["properties"]["parameters"]["model_key"]["defaultValue"] == "CHANGE_ME_MODEL_KEY"


@pytest.mark.parametrize("models,message", [
    ([], "at least one model"),
    ("SalesA", "at least one model"),
    ([{"model_key": "A", "dataset": "x"}], "missing fields"),
    ([{"model_key": "has space", "dataset": "x", "queryfile": "/lakehouse/default/q.json"}], "no spaces"),
    ([{"model_key": "A", "dataset": "", "queryfile": "/lakehouse/default/q.json"}], "dataset is empty"),
    ([{"model_key": "A", "dataset": "x", "queryfile": "/tmp/q.json"}], "must start with /lakehouse/default/"),
    ([{"model_key": "A", "dataset": "x", "queryfile": "/lakehouse/default/my file.json"}], "no spaces"),
    ([{"model_key": "A", "dataset": "x", "queryfile": "/lakehouse/default/q.json"}] * 2, "is repeated"),
])
def test_invalid_models_fail_before_anything_is_created(env, models, message):
    fake, lake = env
    with pytest.raises(ValueError, match=message):
        run_installer(fake, lake, MODELS=models)
    assert fake.items == {}


def test_a_modified_zip_is_rejected(env):
    fake, lake = env
    make_zip(lake.root / "Files" / "deploy" / "FabricLoadTest_v3_package.zip",
             mutate={"pipelines/PL_PerfTest_Ramp_v3.json": lambda raw: raw + b" "})
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_installer(fake, lake)
    assert fake.items == {}


def test_missing_zip_and_missing_or_foreign_lakehouse_have_clear_errors(env):
    fake, lake = env
    with pytest.raises(FileNotFoundError, match="Package not found"):
        run_installer(fake, lake, PACKAGE_PATH="Files/deploy/nope.zip")
    with pytest.raises(RuntimeError, match="no default lakehouse"):
        run_installer(fake, lake, lh_id=None)
    with pytest.raises(RuntimeError, match="another workspace"):
        run_installer(fake, lake, lh_ws=OTHER_WS)
    assert fake.items == {}


def test_a_hardcoded_id_from_another_workspace_is_detected_after_deploy(env):
    fake, lake = env
    foreign = "0badf00d-0000-4000-8000-00000000000a"
    make_zip(lake.root / "Files" / "deploy" / "FabricLoadTest_v3_package.zip",
             mutate={"pipelines/PL_PerfTest_Ramp_v3.json": lambda raw: raw.replace(b'"description"', f'"x-origin": "{foreign}", "description"'.encode(), 1)},
             manifest_hashes_from_mutated=True)
    with pytest.raises(RuntimeError, match="problem"):
        run_installer(fake, lake)


def test_an_id_of_another_existing_item_is_also_a_leftover(env):
    fake, lake = env
    other = fake.add("Notebook", "SomethingElse", {"parts": []})["id"]
    make_zip(lake.root / "Files" / "deploy" / "FabricLoadTest_v3_package.zip",
             mutate={"notebooks/RunLoadTest_v3.ipynb": lambda raw: raw.replace(b"concurrent_threads", f"concurrent_threads # {other}".encode(), 1)},
             manifest_hashes_from_mutated=True)
    with pytest.raises(RuntimeError, match="problem"):
        run_installer(fake, lake)


@pytest.mark.parametrize("workspace_name,lakehouse_name", [("SourceLakehouse", "SourceLakehouse"), ("AdventureWorks Sales", "source-workspace")])
def test_names_that_resemble_the_origin_are_not_flagged(env, workspace_name, lakehouse_name):
    fake, lake = env
    fake.add("SemanticModel", "AdventureWorks Sales")
    _, out = run_installer(fake, lake, ws_name=workspace_name, lh_name=lakehouse_name,
                           MODELS=[{"model_key": "AdventureWorksSales", "dataset": "AdventureWorks Sales", "workspace": "",
                                    "queryfile": "/lakehouse/default/Files/PerfScenarios/Queries/PowerBIPerformanceData.json"}])
    assert "VERIFICATION OK" in out
    dependencies = json.loads(fake.definition_text("RunLoadTest_v3"))["metadata"]["dependencies"]["lakehouse"]
    assert dependencies["default_lakehouse_name"] == lakehouse_name


def test_summary_suggests_models_and_lists_navigation_files(env):
    fake, lake = env
    fake.add("SemanticModel", "AdventureWorks Sales 1")
    queries = lake.root / "Files" / "PerfScenarios" / "Queries"
    queries.mkdir(parents=True)
    (queries / "PowerBIPerformanceData.json").write_text("[]")
    _, out = run_installer(fake, lake)
    assert "PowerBIPerformanceData.json" in out
    suggestion = json.loads(next(l for l in out.splitlines() if l.startswith("[{")))
    assert suggestion[0]["model_key"] == "AdventureWorksSales1" and suggestion[0]["dataset"] == "AdventureWorks Sales 1"
    assert suggestion[0]["queryfile"].endswith("/PowerBIPerformanceData_AdventureWorksSales1.json")
