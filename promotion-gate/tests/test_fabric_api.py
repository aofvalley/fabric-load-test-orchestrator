import json

import pytest

from promotion_gate.fabric_api import FabricClient, FabricError, pipeline_definition


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, content=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = content if content is not None else (json.dumps(body).encode() if body is not None else b"")
        self.text = self.content.decode(errors="replace")

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, json=None, data=None, headers=None, timeout=None):
        self.calls.append((method, url, json, data))
        for (m, frag), resp in self.routes.items():
            if m == method and frag in url:
                return resp(url) if callable(resp) else resp
        return FakeResponse(404, {"error": "not found"})

    def get(self, url, headers=None, timeout=None):
        return self.request("GET", url, headers=headers)


def client(routes):
    s = FakeSession(routes)
    return FabricClient(token_provider=lambda r: f"tok-{r}", session=s, poll_seconds=0), s


def test_upsert_creates_then_updates():
    fc, s = client({
        ("GET", "/items?type=Notebook"): FakeResponse(200, {"value": []}),
        ("POST", "/workspaces/ws/items"): FakeResponse(201, {"id": "new-id"}),
    })
    assert fc.upsert_item("ws", "NB", "Notebook", {"parts": []}, overwrite=False) == "new-id"
    fc2, s2 = client({
        ("GET", "/items?type=Notebook"): FakeResponse(200, {"value": [{"id": "old", "displayName": "NB"}]}),
        ("POST", "/updateDefinition"): FakeResponse(200, {}),
    })
    assert fc2.upsert_item("ws", "NB", "Notebook", {"parts": []}, overwrite=True) == "old"
    with pytest.raises(FabricError):
        fc2.upsert_item("ws", "NB", "Notebook", {"parts": []}, overwrite=False)


def test_run_job_returns_location_and_sends_parameters():
    fc, s = client({("POST", "/jobs/instances?jobType=Pipeline"): FakeResponse(202, None, {"Location": "https://x/jobs/instances/j1"})})
    assert fc.run_job("ws", "pl", "Pipeline", {"dataset": "Ventas"}).endswith("/j1")
    assert s.calls[0][2] == {"executionData": {"parameters": {"dataset": "Ventas"}}}


def test_onelake_write_create_append_flush():
    fc, s = client({("PUT", "onelake"): FakeResponse(201), ("PATCH", "onelake"): FakeResponse(202)})
    fc.onelake_write("ws", "lh", "Files/a.txt", b"hola")
    assert [c[0] for c in s.calls] == ["PUT", "PATCH", "PATCH"]
    assert "resource=file" in s.calls[0][1] and "action=append&position=0" in s.calls[1][1]
    assert "action=flush&position=4" in s.calls[2][1]


def test_deploy_stage_body():
    fc, s = client({("POST", "/deploymentPipelines/dp/deploy"): FakeResponse(200, {})})
    fc.deploy_stage("dp", "s0", "s1", [{"sourceItemId": "m", "itemType": "SemanticModel"}], "nota")
    assert s.calls[0][2] == {"sourceStageId": "s0", "targetStageId": "s1",
                             "items": [{"sourceItemId": "m", "itemType": "SemanticModel"}], "note": "nota"}


def test_pipeline_definition_requires_all_placeholders():
    raw = '{"a": "{{WORKSPACE_ID}}", "b": "{{NOTEBOOK:X}}"}'
    with pytest.raises(ValueError):
        pipeline_definition(raw, {"WORKSPACE_ID": "w"})
    d = pipeline_definition(raw, {"WORKSPACE_ID": "w", "NOTEBOOK:X": "n"})
    assert d["parts"][0]["path"] == "pipeline-content.json"


def test_token_is_refreshed_near_expiry_and_on_401():
    import time
    issued = []

    def provider(resource):
        issued.append(resource)
        return (f"tok{len(issued)}", time.time() + (60 if len(issued) == 1 else 3600))

    responses = iter([FakeResponse(401, {}), FakeResponse(200, {"ok": 1})])
    s = FakeSession({("GET", "/workspaces/ws"): lambda url: next(responses)})
    fc = FabricClient(token_provider=provider, session=s, poll_seconds=0)
    assert fc.request("GET", "workspaces/ws") == {"ok": 1}
    assert len(issued) == 2  # el 401 fuerza un token nuevo
    fc._cache["https://api.fabric.microsoft.com"] = ("viejo", time.time() + 10)
    fc._headers("https://api.fabric.microsoft.com")
    assert len(issued) == 3  # a menos de 5 min de caducar se renueva antes de usarlo


def test_az_is_resolved_with_which(monkeypatch):
    from promotion_gate import fabric_api

    monkeypatch.setattr(fabric_api.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError):
        fabric_api.az_token("https://api.fabric.microsoft.com")
