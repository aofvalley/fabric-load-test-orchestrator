import { client, ensureRayfinSession, rayfinUser } from './rayfinClient';
import type { RunRecord } from './types';

/**
 * Historial de runs. Con sesión Rayfin, la entidad GateRun (compartida por el equipo); sin ella (local o demo),
 * localStorage de este navegador. La fuente oficial de auditoría sigue siendo la tabla Delta gate_runs.
 */
const LOCAL_KEY = 'promotion-gate.runs.v1';

export interface RunStore {
  shared: boolean;
  list(): Promise<RunRecord[]>;
  save(run: RunRecord): Promise<RunRecord>;
  update(run: RunRecord, patch: Partial<RunRecord>): Promise<RunRecord>;
}

export class LocalRunStore implements RunStore {
  shared = false;
  constructor(private readonly seed: RunRecord[] = []) {}

  private read(): RunRecord[] {
    try {
      const raw = localStorage.getItem(LOCAL_KEY);
      if (raw) return JSON.parse(raw) as RunRecord[];
    } catch { /* almacenamiento bloqueado */ }
    return [...this.seed];
  }

  private write(runs: RunRecord[]) {
    try { localStorage.setItem(LOCAL_KEY, JSON.stringify(runs)); } catch { /* sin persistencia */ }
  }

  async list() {
    return this.read().sort((a, b) => b.started_at.localeCompare(a.started_at));
  }

  async save(run: RunRecord) {
    const runs = this.read().filter((r) => r.run_id !== run.run_id);
    this.write([run, ...runs]);
    return run;
  }

  async update(run: RunRecord, patch: Partial<RunRecord>) {
    const next = { ...run, ...patch };
    this.write(this.read().map((r) => (r.run_id === run.run_id ? next : r)));
    return next;
  }
}

const FIELDS = ['id', 'run_id', 'user_id', 'requested_by', 'workspace_id', 'workspace_name', 'dataset_id', 'dataset_name',
  'report_id', 'report_name', 'model_key', 'scenario_path', 'scenario_source', 'ramp_levels', 'target_level',
  'gate_config_json', 'pipeline_job_id', 'status', 'verdict', 'promotable', 'started_at', 'finished_at', 'promoted_at',
  'promoted_by', 'promoted_to'] as const;

function fromRow(r: Record<string, unknown>): RunRecord {
  const d = (v: unknown) => (v instanceof Date ? v.toISOString() : v == null ? undefined : String(v));
  return {
    ...(r as unknown as RunRecord),
    target_level: Number(r.target_level),
    promotable: r.promotable == null ? undefined : r.promotable === true || r.promotable === 'true',
    started_at: d(r.started_at) ?? new Date().toISOString(),
    finished_at: d(r.finished_at),
    promoted_at: d(r.promoted_at),
  };
}

function toRow(run: Partial<RunRecord>): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(run)) {
    if (k === 'id' || v === undefined) continue;
    row[k] = ['started_at', 'finished_at', 'promoted_at'].includes(k) ? new Date(String(v)) : v;
  }
  return row;
}

export class RayfinRunStore implements RunStore {
  shared = true;

  async list() {
    const rows = (await client.data.GateRun.select([...FIELDS] as never).orderBy({ started_at: 'desc' } as never)
      .first(200).execute()) as unknown as Record<string, unknown>[];
    return rows.map(fromRow);
  }

  async save(run: RunRecord) {
    const user = rayfinUser();
    const created = (await client.data.GateRun.create(toRow({ ...run, user_id: user.id ?? run.user_id }) as never)) as unknown;
    return fromRow({ ...run, ...(created as Record<string, unknown>) });
  }

  async update(run: RunRecord, patch: Partial<RunRecord>) {
    if (!run.id) return { ...run, ...patch };
    await client.data.GateRun.update({ id: run.id } as never, toRow(patch) as never);
    return { ...run, ...patch };
  }
}

export async function openRunStore(seed: RunRecord[] = []): Promise<RunStore> {
  if (await ensureRayfinSession()) {
    try {
      const store = new RayfinRunStore();
      await store.list();
      return store;
    } catch { /* tabla aún no aplicada (rayfin up db apply) o sin permisos: historial local */ }
  }
  return new LocalRunStore(seed);
}
