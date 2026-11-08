import type { ActivityRun, JobInstance, Stage } from './fabric';
import type { Verdict } from './types';

/** Número de certificado: GATE-AAAAMMDD-HHMM-XXXX. Seguro para carpetas y para test_name_prefix del orquestador. */
export function makeRunId(now = new Date(), rand = Math.random): string {
  const p = (n: number) => String(n).padStart(2, '0');
  const stamp = `${now.getUTCFullYear()}${p(now.getUTCMonth() + 1)}${p(now.getUTCDate())}-${p(now.getUTCHours())}${p(now.getUTCMinutes())}`;
  const suffix = Math.floor(rand() * 0xffff).toString(16).toUpperCase().padStart(4, '0');
  return `GATE-${stamp}-${suffix}`;
}

/** model_key del orquestador: letras, dígitos, - y _; corto y estable a partir del nombre del modelo. */
export function modelKey(name: string): string {
  const key = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9_-]+/g, '_')
    .replace(/_+/g, '_').replace(/^_|_$/g, '').slice(0, 40);
  return key || 'modelo';
}

export function parseRamp(text: string): number[] {
  const levels = text.split(/[\s,;]+/).map((s) => Number(s.trim())).filter((n) => Number.isInteger(n) && n > 0);
  return [...new Set(levels)].sort((a, b) => a - b);
}

export function rampProblems(levels: number[], target: number): string[] {
  const out: string[] = [];
  if (!levels.length) out.push('La rampa necesita al menos un nivel de usuarios.');
  if (levels.some((l) => l > 300)) out.push('El orquestador admite como máximo 300 usuarios por nivel.');
  if (levels.length && Math.max(...levels) < target) out.push(`La rampa no llega a los ${target} usuarios objetivo: el gate lo marcará como aviso.`);
  if (levels.length === 1) out.push('Con un solo nivel no se puede medir cómo escala el modelo.');
  return out;
}

export interface LaunchForm {
  runId: string;
  datasetName: string;
  workspaceName: string;
  modelKey: string;
  queryfile: string;
  rampLevels: number[];
  targetLevel: number;
  sku: string;
  iterations: number;
  thinkTimes: boolean;
  thinkTimeScale: number;
  rampUpSec: number;
  /** UPN separados por comas o la ruta de un fichero del lakehouse con un UPN por línea. */
  rlsUsers: string;
  /** false = si la revisión del modelo falla, el pipeline no gasta capacidad en el test de carga. */
  fullRun: boolean;
  capacityId?: string;
  capacityMetricsWorkspace: string;
  toolingWorkspaceId: string;
  requestedBy: string;
}

/** Ajustes de este run sobre gate.yaml: solo hechos de producción (usuarios objetivo y SKU), nunca los SLO del equipo. */
export function gateOverride(f: Pick<LaunchForm, 'targetLevel' | 'sku'>): Record<string, unknown> {
  return { load_test: { target_level: f.targetLevel }, model_review: { sku: f.sku } };
}

/** Usuarios RLS: una lista de UPN va a `rls_users` y una ruta (/lakehouse/... o *.txt) a `rls_users_file`. */
export function rlsParams(value: string): { rls_users: string; rls_users_file: string } {
  const v = value.trim();
  const isFile = /^\/lakehouse\//i.test(v) || /^Files\//i.test(v) || /\.txt$/i.test(v);
  if (!isFile) return { rls_users: v, rls_users_file: '' };
  return { rls_users: '', rls_users_file: v.startsWith('Files/') ? `/lakehouse/default/${v}` : v };
}

/** Parámetros de PL_PromotionGate (mismos nombres que pipelines/PL_PromotionGate.json). */
export function pipelineParams(f: LaunchForm): Record<string, unknown> {
  return {
    run_id: f.runId,
    dataset: f.datasetName,
    model_workspace: f.workspaceName,
    model_key: f.modelKey,
    queryfile: f.queryfile,
    ramp_levels: f.rampLevels,
    iterations: f.iterations,
    enable_think_times: f.thinkTimes,
    think_time_scale: f.thinkTimeScale,
    ramp_up_sec: f.rampUpSec,
    ...rlsParams(f.rlsUsers),
    stop_on_review_fail: !f.fullRun,
    capacity_metrics_workspace: f.capacityMetricsWorkspace,
    capacity_id: f.capacityId ?? '',
    tooling_workspace_id: f.toolingWorkspaceId,
    gate_config: JSON.stringify(gateOverride(f)),
    requested_by: f.requestedBy,
    source_ref: 'fabric-app',
  };
}

// ---------- Localizar el job (la API no expone Location por CORS) ----------
export function candidateJobs(jobs: JobInstance[], launchedAt: Date): JobInstance[] {
  const from = launchedAt.getTime() - 120_000;
  return jobs
    .filter((j) => !j.startTimeUtc || Date.parse(j.startTimeUtc.endsWith('Z') ? j.startTimeUtc : `${j.startTimeUtc}Z`) >= from)
    .sort((a, b) => (b.startTimeUtc ?? '').localeCompare(a.startTimeUtc ?? ''));
}

export function activitiesMentionRun(runs: ActivityRun[], runId: string): boolean {
  return runs.some((r) => JSON.stringify(r.input ?? '').includes(runId));
}

// ---------- Fases ----------
export type PhaseState = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export const PHASES = [
  { id: 'review', label: 'Buenas prácticas', detail: 'BPA y VertiPaq', activity: 'NB_Gate_ModelReview' },
  { id: 'load', label: 'Test de carga', detail: 'Rampa de usuarios', activity: 'Run_LoadTest' },
  { id: 'loadreport', label: 'Informe de carga', detail: 'Percentiles y errores', activity: 'NB_Gate_LoadTestReport' },
  { id: 'capacity', label: 'Capacity Metrics', detail: 'Espera a que lleguen las métricas y lee utilización y throttling', activity: 'NB_Gate_CapacityMetrics' },
  { id: 'verdict', label: 'Veredicto', detail: 'Decisión e informe', activity: 'NB_Gate_Verdict' },
] as const;

export type PhaseId = (typeof PHASES)[number]['id'];

export interface PhaseStatus {
  id: PhaseId;
  label: string;
  detail: string;
  state: PhaseState;
  startedAt?: string;
  durationMs?: number;
  message?: string;
}

function activityState(status: string): PhaseState {
  const s = status.toLowerCase();
  if (s === 'succeeded') return 'done';
  if (s === 'failed' || s === 'cancelled' || s === 'canceled') return 'failed';
  if (s === 'skipped') return 'skipped';
  return 'running';
}

export function phaseStatuses(runs: ActivityRun[], jobStatus: string): PhaseStatus[] {
  const finished = ['Completed', 'Failed', 'Cancelled', 'Deduped'].includes(jobStatus);
  return PHASES.map((p) => {
    const act = [...runs].reverse().find((r) => r.activityName === p.activity);
    if (!act) return { id: p.id, label: p.label, detail: p.detail, state: finished ? 'skipped' : 'pending' };
    let state = activityState(act.status);
    // NB_Gate_* sale con exitValue aunque el gate sea FAIL; la actividad «Succeeded» es la fase hecha.
    if (state === 'running' && finished) state = 'failed';
    return {
      id: p.id, label: p.label, detail: p.detail, state,
      startedAt: act.activityRunStart, durationMs: act.durationInMs,
      message: act.error?.message || undefined,
    };
  });
}

export function exitValue<T = Record<string, unknown>>(runs: ActivityRun[], activity: string): T | null {
  const raw = [...runs].reverse().find((r) => r.activityName === activity)?.output?.result?.exitValue;
  if (!raw) return null;
  try { return JSON.parse(raw) as T; } catch { return null; }
}

// ---------- Promoción ----------
export interface PromotionPath { pipelineId: string; pipelineName: string; source: Stage; target: Stage }

/** Stage cuyo workspace es el del modelo y el siguiente en orden: la ruta natural test → producción. */
export function promotionPath(pipelineId: string, pipelineName: string, stages: Stage[], workspaceId: string): PromotionPath | null {
  const sorted = [...stages].sort((a, b) => a.order - b.order);
  const i = sorted.findIndex((s) => s.workspaceId?.toLowerCase() === workspaceId.toLowerCase());
  if (i < 0 || i === sorted.length - 1) return null;
  return { pipelineId, pipelineName, source: sorted[i], target: sorted[i + 1] };
}

export function promotionBlockers(v: Verdict | null, datasetId: string, alreadyPromoted?: string): string[] {
  const out: string[] = [];
  if (!v) out.push('El gate no ha emitido veredicto.');
  else {
    if (!v.promotable) out.push(`Veredicto ${v.verdict}: el modelo no es promocionable.`);
    if (v.context.item_id && v.context.item_id.toLowerCase() !== datasetId.toLowerCase())
      out.push('El veredicto es de otro modelo.');
  }
  if (alreadyPromoted) out.push(`Este run ya se promocionó el ${alreadyPromoted}.`);
  return out;
}
