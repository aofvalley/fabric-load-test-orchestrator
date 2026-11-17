import { getToken, type ScopeSet } from './msal';

const FABRIC = 'https://api.fabric.microsoft.com/v1';
const PBI = 'https://api.powerbi.com/v1.0/myorg';
const ONELAKE = 'https://onelake.dfs.fabric.microsoft.com';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

function friendly(status: number, body: string): string {
  let detail = body.slice(0, 300);
  try {
    const j = JSON.parse(body);
    detail = j.message ?? j.error?.message ?? j.errorCode ?? detail;
  } catch { /* texto plano */ }
  if (status === 401) return `Sesión caducada o sin consentimiento (401). ${detail}`;
  if (status === 403) return `Tu usuario no tiene permiso para esta operación (403). ${detail}`;
  if (status === 404) return `No encontrado (404). ${detail}`;
  if (status === 429) return 'Fabric está limitando las peticiones (429). Espera unos segundos.';
  return `Error ${status}. ${detail}`;
}

async function call(url: string, scopes: ScopeSet, init: RequestInit = {}, retry = true): Promise<Response> {
  const token = await getToken(scopes);
  const res = await fetch(url, { ...init, headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` } });
  if (res.status === 401 && retry) {
    await getToken(scopes, { forceRefresh: true });
    return call(url, scopes, init, false);
  }
  if (res.status === 429 && retry) {
    await new Promise((r) => setTimeout(r, 4000));
    return call(url, scopes, init, false);
  }
  if (!res.ok) throw new ApiError(res.status, friendly(res.status, await res.text().catch(() => '')));
  return res;
}

async function json<T>(url: string, scopes: ScopeSet, init?: RequestInit): Promise<T> {
  const res = await call(url, scopes, init);
  const text = await res.text();
  return (text ? JSON.parse(text) : {}) as T;
}

async function paged<T>(url: string, scopes: ScopeSet): Promise<T[]> {
  const out: T[] = [];
  let next: string | undefined = url;
  while (next) {
    const page: { value?: T[]; continuationUri?: string } = await json(next, scopes);
    out.push(...(page.value ?? []));
    next = page.continuationUri ?? undefined;
  }
  return out;
}

const byName = <T extends { displayName?: string; name?: string }>(a: T, b: T) =>
  (a.displayName ?? a.name ?? '').localeCompare(b.displayName ?? b.name ?? '', 'es', { sensitivity: 'base' });

// ---------- Descubrimiento ----------
export interface Workspace { id: string; displayName: string; capacityId?: string; type?: string }
export interface Item { id: string; displayName: string; type: string; description?: string }
export interface Report { id: string; name: string; datasetId: string; webUrl: string }

export async function listWorkspaces(): Promise<Workspace[]> {
  return (await paged<Workspace>(`${FABRIC}/workspaces`, 'fabricRead')).filter((w) => w.type !== 'Personal').sort(byName);
}

export function getWorkspace(id: string): Promise<Workspace> {
  return json(`${FABRIC}/workspaces/${id}`, 'fabricRead');
}

export async function listItems(workspaceId: string, type?: string): Promise<Item[]> {
  const q = type ? `?type=${encodeURIComponent(type)}` : '';
  return (await paged<Item>(`${FABRIC}/workspaces/${workspaceId}/items${q}`, 'fabricRead')).sort(byName);
}

export async function findItem(workspaceId: string, name: string, type: string): Promise<Item | undefined> {
  return (await listItems(workspaceId, type)).find((i) => i.displayName === name);
}

export async function listReports(workspaceId: string): Promise<Report[]> {
  const r = await json<{ value: Report[] }>(`${PBI}/groups/${workspaceId}/reports`, 'powerbi');
  return (r.value ?? []).sort(byName);
}

/** DAX contra el modelo con la identidad del usuario (requiere el ajuste de tenant «Dataset Execute Queries REST API»). */
export async function executeDax(datasetId: string, dax: string): Promise<Record<string, unknown>[]> {
  const r = await json<{ results: { tables: { rows: Record<string, unknown>[] }[]; error?: { message?: string } }[] }>(
    `${PBI}/datasets/${datasetId}/executeQueries`, 'powerbi', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ queries: [{ query: dax }], serializerSettings: { includeNulls: true } }),
    });
  const first = r.results?.[0];
  if (first?.error) throw new ApiError(400, first.error.message ?? 'Error DAX');
  return first?.tables?.[0]?.rows ?? [];
}

// ---------- Jobs de pipeline ----------
export interface JobInstance {
  id: string;
  status: string;
  invokeType?: string;
  jobType?: string;
  startTimeUtc?: string;
  endTimeUtc?: string;
  failureReason?: { message?: string; errorCode?: string } | null;
}

export async function runPipeline(workspaceId: string, pipelineId: string, parameters: Record<string, unknown>): Promise<void> {
  await call(`${FABRIC}/workspaces/${workspaceId}/items/${pipelineId}/jobs/instances?jobType=Pipeline`, 'fabricRun', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ executionData: { parameters } }),
  });
}

export async function listJobs(workspaceId: string, itemId: string): Promise<JobInstance[]> {
  return paged<JobInstance>(`${FABRIC}/workspaces/${workspaceId}/items/${itemId}/jobs/instances`, 'fabricRun');
}

export function getJob(workspaceId: string, itemId: string, jobId: string): Promise<JobInstance> {
  return json(`${FABRIC}/workspaces/${workspaceId}/items/${itemId}/jobs/instances/${jobId}`, 'fabricRun');
}

export async function cancelJob(workspaceId: string, itemId: string, jobId: string): Promise<void> {
  await call(`${FABRIC}/workspaces/${workspaceId}/items/${itemId}/jobs/instances/${jobId}/cancel`, 'fabricRun', { method: 'POST' });
}

export interface ActivityRun {
  activityName: string;
  activityType: string;
  status: string;
  activityRunStart?: string;
  activityRunEnd?: string;
  durationInMs?: number;
  input?: unknown;
  output?: { result?: { exitValue?: string } } & Record<string, unknown>;
  error?: { message?: string; errorCode?: string };
}

export async function queryActivityRuns(workspaceId: string, jobId: string, since: Date): Promise<ActivityRun[]> {
  const body = {
    filters: [], orderBy: [{ orderBy: 'ActivityRunStart', order: 'ASC' }],
    lastUpdatedAfter: new Date(since.getTime() - 3600_000).toISOString(),
    lastUpdatedBefore: new Date(Date.now() + 3600_000).toISOString(),
  };
  const r = await json<ActivityRun[] | { value: ActivityRun[] }>(
    `${FABRIC}/workspaces/${workspaceId}/datapipelines/pipelineruns/${jobId}/queryactivityruns`, 'fabricRun',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  return Array.isArray(r) ? r : r.value ?? [];
}

// ---------- Deployment pipelines ----------
export interface DeploymentPipeline { id: string; displayName: string }
export interface Stage { id: string; displayName: string; order: number; workspaceId?: string; workspaceName?: string; isPublic?: boolean }

export async function listDeploymentPipelines(): Promise<DeploymentPipeline[]> {
  return paged<DeploymentPipeline>(`${FABRIC}/deploymentPipelines`, 'fabricDeploy');
}

export async function listStages(pipelineId: string): Promise<Stage[]> {
  return (await paged<Stage>(`${FABRIC}/deploymentPipelines/${pipelineId}/stages`, 'fabricDeploy')).sort((a, b) => a.order - b.order);
}

export interface DeployOperation { id: string; status: string; executionStartTime?: string; executionEndTime?: string; note?: { content?: string } }

export async function deployStage(pipelineId: string, sourceStageId: string, targetStageId: string,
  items: { sourceItemId: string; itemType: string }[], note: string): Promise<void> {
  await call(`${FABRIC}/deploymentPipelines/${pipelineId}/deploy`, 'fabricDeploy', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sourceStageId, targetStageId, items, note: note.slice(0, 1024) }),
  });
}

export async function listDeployOperations(pipelineId: string): Promise<DeployOperation[]> {
  return paged<DeployOperation>(`${FABRIC}/deploymentPipelines/${pipelineId}/operations`, 'fabricDeploy');
}

// ---------- OneLake (DFS) ----------
const dfsHeaders = { 'x-ms-version': '2023-11-03' };

export async function onelakeRead(workspaceId: string, lakehouseId: string, path: string): Promise<string | null> {
  try {
    const res = await call(`${ONELAKE}/${workspaceId}/${lakehouseId}/${path}`, 'onelake', { headers: dfsHeaders });
    return await res.text();
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function onelakeWrite(workspaceId: string, lakehouseId: string, path: string, data: Blob | string): Promise<void> {
  const url = `${ONELAKE}/${workspaceId}/${lakehouseId}/${path}`;
  const blob = typeof data === 'string' ? new Blob([data]) : data;
  // Cuerpo vacío explícito: sin él el navegador no manda Content-Length y OneLake responde 400 MissingRequiredHeader.
  await call(`${url}?resource=file`, 'onelake', { method: 'PUT', headers: dfsHeaders, body: '' });
  if (blob.size) await call(`${url}?action=append&position=0`, 'onelake', { method: 'PATCH', headers: dfsHeaders, body: blob });
  await call(`${url}?action=flush&position=${blob.size}`, 'onelake', { method: 'PATCH', headers: dfsHeaders, body: '' });
}

export interface PathEntry { name: string; isDirectory: boolean; contentLength: number; lastModified: string }

export async function onelakeList(workspaceId: string, lakehouseId: string, directory: string): Promise<PathEntry[]> {
  try {
    const url = `${ONELAKE}/${workspaceId}?resource=filesystem&recursive=false&directory=${encodeURIComponent(`${lakehouseId}/${directory}`)}`;
    const r = await json<{ paths?: { name: string; isDirectory?: string | boolean; contentLength?: string; lastModified?: string }[] }>(
      url, 'onelake', { headers: dfsHeaders });
    return (r.paths ?? []).map((p) => ({
      name: p.name.split('/').pop() ?? p.name,
      isDirectory: p.isDirectory === true || p.isDirectory === 'true',
      contentLength: Number(p.contentLength ?? 0),
      lastModified: p.lastModified ?? '',
    }));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return [];
    throw e;
  }
}
