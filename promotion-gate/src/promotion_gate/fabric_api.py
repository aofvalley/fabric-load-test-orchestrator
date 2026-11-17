"""Cliente mínimo de la API REST de Fabric y de OneLake. Token con `az account get-access-token` (local o CI con OIDC)."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from typing import Any, Callable

import requests

FABRIC = "https://api.fabric.microsoft.com/v1"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
FABRIC_SCOPE = "https://api.fabric.microsoft.com"
STORAGE_SCOPE = "https://storage.azure.com"


def _az() -> str:
    exe = shutil.which("az")  # en Windows resuelve az.cmd
    if not exe:
        raise RuntimeError("No se encuentra Azure CLI (az) en el PATH.")
    return exe


def _github_oidc_relogin() -> bool:
    """En GitHub Actions con OIDC el login de az caduca en ~1 h: pide un id token nuevo y vuelve a hacer login."""
    url, req = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    client, tenant = os.environ.get("AZURE_CLIENT_ID"), os.environ.get("AZURE_TENANT_ID")
    if not (url and req and client and tenant):
        return False
    r = requests.get(url + "&audience=api://AzureADTokenExchange", headers={"Authorization": f"Bearer {req}"}, timeout=30)
    if r.status_code != 200:
        return False
    out = subprocess.run([_az(), "login", "--service-principal", "-u", client, "--tenant", tenant, "--federated-token",
                          r.json()["value"], "--allow-no-subscriptions", "-o", "none"], capture_output=True, text=True)
    return out.returncode == 0


def az_token(resource: str) -> tuple[str, float]:
    """Token y caducidad (epoch) de Azure CLI para el recurso."""
    cmd = [_az(), "account", "get-access-token", "--resource", resource, "-o", "json"]
    # Cuenta del tenant de Fabric: con varias sesiones de az, la suscripción fija el usuario (p. ej. admin del tenant dev).
    if os.environ.get("SMGATE_AZ_SUBSCRIPTION"):
        cmd += ["--subscription", os.environ["SMGATE_AZ_SUBSCRIPTION"]]
    elif os.environ.get("SMGATE_AZ_TENANT"):
        cmd += ["--tenant", os.environ["SMGATE_AZ_TENANT"]]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if out.returncode != 0 and _github_oidc_relogin():
        out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError("No hay token de Azure CLI: ejecuta az login (o azure/login en CI). " + out.stderr.strip()[:300])
    data = json.loads(out.stdout)
    expires = data.get("expires_on")
    try:
        expires = float(expires)
    except (TypeError, ValueError):
        expires = time.time() + 30 * 60
    return data["accessToken"], expires


class FabricError(RuntimeError):
    pass


class FabricClient:
    def __init__(self, token_provider: Callable[[str], str] = az_token, session: requests.Session | None = None,
                 poll_seconds: float = 5.0):
        self._token = token_provider
        self._s = session or requests.Session()
        self._poll = poll_seconds
        self._cache: dict[str, tuple[str, float]] = {}

    def _headers(self, resource: str) -> dict[str, str]:
        cached = self._cache.get(resource)
        if not cached or cached[1] - time.time() < 300:
            got = self._token(resource)
            if isinstance(got, str):
                got = (got, time.time() + 30 * 60)
            if got[1] - time.time() < 300 and _github_oidc_relogin():
                got = self._token(resource)
            self._cache[resource] = got
        return {"Authorization": f"Bearer {self._cache[resource][0]}"}

    def _send(self, method: str, url: str, resource: str, **kw) -> requests.Response:
        r = self._s.request(method, url, headers=self._headers(resource), **kw)
        if r.status_code == 401:
            self._cache.pop(resource, None)
            r = self._s.request(method, url, headers=self._headers(resource), **kw)
        return r

    # ---------- Fabric REST ----------
    def request(self, method: str, path: str, body: Any = None, lro: bool = True) -> Any:
        url = path if path.startswith("http") else f"{FABRIC}/{path.lstrip('/')}"
        for attempt in range(6):
            r = self._send(method, url, FABRIC_SCOPE, json=body, timeout=120)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "10")))
                continue
            break
        if r.status_code >= 400:
            raise FabricError(f"{method} {url} → {r.status_code}: {r.text[:500]}")
        if r.status_code == 202 and lro and "Location" in r.headers and "/jobs/instances" not in url:
            return self._wait_operation(r.headers["Location"], int(r.headers.get("Retry-After", "2")))
        if r.status_code == 202:
            return {"_location": r.headers.get("Location")}
        return r.json() if r.content else {}

    def _wait_operation(self, location: str, retry_after: int) -> Any:
        while True:
            time.sleep(max(retry_after, 1))
            r = self._send("GET", location, FABRIC_SCOPE, timeout=60)
            if r.status_code >= 400:
                raise FabricError(f"Operación {location} → {r.status_code}: {r.text[:500]}")
            state = (r.json() if r.content else {}).get("status")
            if state in ("Succeeded", None):
                res = self._send("GET", location.rstrip("/") + "/result", FABRIC_SCOPE, timeout=60)
                return res.json() if res.status_code == 200 and res.content else {}
            if state in ("Failed", "Cancelled"):
                raise FabricError(f"Operación {state}: {r.text[:500]}")

    def list_items(self, workspace_id: str, item_type: str | None = None) -> list[dict[str, Any]]:
        url = f"workspaces/{workspace_id}/items" + (f"?type={item_type}" if item_type else "")
        items: list[dict[str, Any]] = []
        while url:
            page = self.request("GET", url)
            items += page.get("value", [])
            url = page.get("continuationUri")
        return items

    def find_item(self, workspace_id: str, name: str, item_type: str) -> dict[str, Any] | None:
        return next((i for i in self.list_items(workspace_id, item_type) if i["displayName"] == name), None)

    def upsert_item(self, workspace_id: str, name: str, item_type: str, definition: dict[str, Any],
                    overwrite: bool, description: str = "") -> str:
        existing = self.find_item(workspace_id, name, item_type)
        if existing:
            if not overwrite:
                raise FabricError(f"'{name}' ya existe y overwrite = False")
            self.request("POST", f"workspaces/{workspace_id}/items/{existing['id']}/updateDefinition",
                         {"definition": definition})
            return existing["id"]
        created = self.request("POST", f"workspaces/{workspace_id}/items",
                               {"displayName": name, "type": item_type, "description": description,
                                "definition": definition})
        return created.get("id") or self.find_item(workspace_id, name, item_type)["id"]

    def run_job(self, workspace_id: str, item_id: str, job_type: str, parameters: dict[str, Any] | None = None) -> str:
        body = {"executionData": {"parameters": parameters}} if parameters else None
        res = self.request("POST", f"workspaces/{workspace_id}/items/{item_id}/jobs/instances?jobType={job_type}", body)
        if not res.get("_location"):
            raise FabricError("La API no devolvió la ubicación del job.")
        return res["_location"]

    def wait_job(self, location: str, timeout_s: int = 6 * 3600, on_poll: Callable[[dict], None] | None = None) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            job = self.request("GET", location)
            if on_poll:
                on_poll(job)
            if job.get("status") in ("Completed", "Failed", "Cancelled", "Deduped"):
                return job
            time.sleep(max(self._poll, 15))
        raise TimeoutError(f"El job no terminó en {timeout_s} s: {location}")

    def deploy_stage(self, deployment_pipeline_id: str, source_stage_id: str, target_stage_id: str,
                     items: list[dict[str, str]], note: str) -> Any:
        """Deployment pipelines de Fabric: despliega solo los items indicados de un stage al siguiente."""
        return self.request("POST", f"deploymentPipelines/{deployment_pipeline_id}/deploy", {
            "sourceStageId": source_stage_id, "targetStageId": target_stage_id,
            "items": items, "note": note[:1024],
        })

    # ---------- OneLake (ADLS Gen2 DFS) ----------
    def _ol(self, workspace_id: str, lakehouse_id: str, path: str) -> str:
        return f"{ONELAKE}/{workspace_id}/{lakehouse_id}/{path.lstrip('/')}"

    def onelake_read(self, workspace_id: str, lakehouse_id: str, path: str) -> bytes | None:
        r = self._send("GET", self._ol(workspace_id, lakehouse_id, path), STORAGE_SCOPE, timeout=120)
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise FabricError(f"OneLake GET {path} → {r.status_code}: {r.text[:300]}")
        return r.content

    def onelake_write(self, workspace_id: str, lakehouse_id: str, path: str, data: bytes) -> None:
        url = self._ol(workspace_id, lakehouse_id, path)
        steps = [("PUT", f"{url}?resource=file", None)]
        if data:
            steps.append(("PATCH", f"{url}?action=append&position=0", data))
        steps.append(("PATCH", f"{url}?action=flush&position={len(data)}", None))
        for method, u, payload in steps:
            r = self._send(method, u, STORAGE_SCOPE, data=payload, timeout=300)
            if r.status_code >= 400:
                raise FabricError(f"OneLake {method} {path} → {r.status_code}: {r.text[:300]}")


def b64(text: str | bytes) -> str:
    raw = text.encode("utf-8") if isinstance(text, str) else text
    return base64.b64encode(raw).decode("ascii")


def pipeline_definition(raw: str, ids: dict[str, str]) -> dict[str, Any]:
    text = raw
    for key, value in ids.items():
        text = text.replace("{{" + key + "}}", value)
    if "{{" in text:
        import re

        raise ValueError("Placeholders sin resolver: " + ", ".join(sorted(set(re.findall(r"\{\{[^}]+\}\}", text)))))
    json.loads(text)
    return {"parts": [{"path": "pipeline-content.json", "payload": b64(text), "payloadType": "InlineBase64"}]}
