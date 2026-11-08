import { parse as parseYaml } from 'yaml';
import { env } from './env';
import * as api from './fabric';
import {
  activitiesMentionRun, candidateJobs, phaseStatuses, pipelineParams, promotionPath,
  type LaunchForm, type PhaseStatus, type PromotionPath,
} from './gate';
import { currentAccount, getToken, signIn, SignInRequiredError } from './msal';
import { parseSchemaRows, SCHEMA_DAX, syntheticScenario } from './scenario';
import type { Evidence, GateConfig } from './types';

export const GATE_PIPELINE = 'PL_PromotionGate';
export const QUERIES_DIR = 'Files/PerfScenarios/Queries';
export const LOGS_DIR = 'Files/PerfScenarios/logs';
export const RUNS_DIR = 'Files/PromotionGate/runs';

export interface Account { name: string; username: string }
export interface ScenarioFile { name: string; path: string; sizeKb: number; modified: string }
export interface LevelProgress { level: number; done: boolean }
export interface Progress {
  jobStatus: string;
  phases: PhaseStatus[];
  levels: LevelProgress[];
  failure?: string;
}
export interface PromoteResult { status: string; operationId?: string }

export interface GateService {
  readonly demo: boolean;
  account(): Promise<Account | null>;
  signIn(): Promise<Account | null>;
  workspaces(): Promise<api.Workspace[]>;
  models(workspaceId: string): Promise<api.Item[]>;
  reports(workspaceId: string): Promise<api.Report[]>;
  capacityOf(workspaceId: string): Promise<string | undefined>;
  scenarios(): Promise<ScenarioFile[]>;
  uploadScenario(fileName: string, content: string): Promise<string>;
  synthesizeScenario(datasetId: string): Promise<string>;
  teamConfig(): Promise<Partial<GateConfig> | null>;
  launch(form: LaunchForm): Promise<void>;
  locateJob(runId: string, launchedAt: Date): Promise<string | null>;
  progress(jobId: string, runId: string, since: Date): Promise<Progress>;
  evidence(runId: string): Promise<Evidence>;
  cancel(jobId: string): Promise<void>;
  promotionPath(workspaceId: string): Promise<PromotionPath | null>;
  promote(path: PromotionPath, items: { sourceItemId: string; itemType: string }[], note: string): Promise<PromoteResult>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const parseJson = <T,>(t: string | null): T | null => {
  if (!t) return null;
  try { return JSON.parse(t) as T; } catch { return null; }
};

export class FabricGateService implements GateService {
  readonly demo = false;
  private pipelineId: string | null = null;
  private ws = env.gateWorkspaceId;
  private lh = env.gateLakehouseId;

  async account() {
    const a = await currentAccount();
    return a ? { name: a.name ?? a.username, username: a.username } : null;
  }

  async signIn() {
    const a = await signIn();
    return a ? { name: a.name ?? a.username, username: a.username } : null;
  }

  workspaces() { return api.listWorkspaces(); }
  models(ws: string) { return api.listItems(ws, 'SemanticModel'); }

  async reports(ws: string) {
    await getToken('powerbi', { interactive: true }).catch(() => undefined);
    return api.listReports(ws);
  }

  async capacityOf(ws: string) {
    return (await api.getWorkspace(ws)).capacityId;
  }

  async scenarios() {
    const files = await api.onelakeList(this.ws, this.lh, QUERIES_DIR);
    return files.filter((f) => !f.isDirectory && f.name.toLowerCase().endsWith('.json')).map((f) => ({
      name: f.name, path: `/lakehouse/default/${QUERIES_DIR}/${f.name}`,
      sizeKb: Math.max(1, Math.round(f.contentLength / 1024)), modified: f.lastModified,
    })).sort((a, b) => b.modified.localeCompare(a.modified));
  }

  async uploadScenario(fileName: string, content: string) {
    const safe = fileName.replace(/[^A-Za-z0-9._-]+/g, '_');
    await getToken('onelake', { interactive: true });
    await api.onelakeWrite(this.ws, this.lh, `${QUERIES_DIR}/${safe}`, content);
    return `/lakehouse/default/${QUERIES_DIR}/${safe}`;
  }

  async synthesizeScenario(datasetId: string) {
    await getToken('powerbi', { interactive: true });
    const [m, c] = await Promise.all([api.executeDax(datasetId, SCHEMA_DAX.measures), api.executeDax(datasetId, SCHEMA_DAX.columns)]);
    const schema = parseSchemaRows(m, c);
    return syntheticScenario(schema.measures, schema.columns);
  }

  async teamConfig() {
    const raw = await api.onelakeRead(this.ws, this.lh, 'Files/PromotionGate/config/gate.yaml').catch((e: unknown) => {
      throw e instanceof SignInRequiredError ? e : new Error(`OneLake: ${(e as Error).message}`);
    });
    if (raw === null) throw new Error('no existe Files/PromotionGate/config/gate.yaml: ejecuta smgate deploy');
    return raw ? (parseYaml(raw) as Partial<GateConfig>) : null;
  }

  private async pipeline(): Promise<string> {
    if (this.pipelineId) return this.pipelineId;
    const item = await api.findItem(this.ws, GATE_PIPELINE, 'DataPipeline');
    if (!item) throw new Error(`No existe ${GATE_PIPELINE} en el workspace del gate: despliégalo con smgate deploy.`);
    this.pipelineId = item.id;
    return item.id;
  }

  async launch(form: LaunchForm) {
    await getToken('fabricRun', { interactive: true });
    await api.runPipeline(this.ws, await this.pipeline(), pipelineParams(form));
  }

  /** La API no expone Location por CORS: se busca el job reciente cuyas actividades llevan este run_id. */
  async locateJob(runId: string, launchedAt: Date) {
    const pid = await this.pipeline();
    for (const job of candidateJobs(await api.listJobs(this.ws, pid), launchedAt).slice(0, 6)) {
      const acts = await api.queryActivityRuns(this.ws, job.id, launchedAt).catch(() => []);
      if (activitiesMentionRun(acts, runId)) return job.id;
    }
    return null;
  }

  async progress(jobId: string, runId: string, since: Date): Promise<Progress> {
    const pid = await this.pipeline();
    const [job, acts] = await Promise.all([api.getJob(this.ws, pid, jobId), api.queryActivityRuns(this.ws, jobId, since)]);
    const levels = await this.levels(runId).catch(() => []);
    return { jobStatus: job.status, phases: phaseStatuses(acts, job.status), levels, failure: job.failureReason?.message };
  }

  /** Niveles de la rampa ya iniciados (carpeta) y terminados (summary.json del orquestador 3.4.0). */
  private async levels(runId: string): Promise<LevelProgress[]> {
    const prefix = `gate-${runId}-`;
    const dirs = (await api.onelakeList(this.ws, this.lh, LOGS_DIR)).filter((d) => d.isDirectory && d.name.startsWith(prefix));
    const out: LevelProgress[] = [];
    for (const d of dirs) {
      const level = Number(/-c(\d+)-\d{8}-\d{6}$/.exec(d.name)?.[1]);
      if (!level) continue;
      const files = await api.onelakeList(this.ws, this.lh, `${LOGS_DIR}/${d.name}`);
      out.push({ level, done: files.some((f) => f.name === 'summary.json') });
    }
    return out.sort((a, b) => a.level - b.level);
  }

  async evidence(runId: string): Promise<Evidence> {
    const base = `${RUNS_DIR}/${runId}`;
    const read = (n: string) => api.onelakeRead(this.ws, this.lh, `${base}/${n}`).catch(() => null);
    const [v, r, l, c, md] = await Promise.all(
      ['verdict.json', 'model_review.json', 'loadtest.json', 'capacity.json', 'report.md'].map(read));
    return { verdict: parseJson(v), review: parseJson(r), loadtest: parseJson(l), capacity: parseJson(c), report: md };
  }

  async cancel(jobId: string) {
    await api.cancelJob(this.ws, await this.pipeline(), jobId);
  }

  async promotionPath(workspaceId: string) {
    await getToken('fabricDeploy', { interactive: true });
    for (const p of await api.listDeploymentPipelines()) {
      const path = promotionPath(p.id, p.displayName, await api.listStages(p.id), workspaceId);
      if (path) return path;
    }
    return null;
  }

  async promote(path: PromotionPath, items: { sourceItemId: string; itemType: string }[], note: string) {
    const before = new Set((await api.listDeployOperations(path.pipelineId)).map((o) => o.id));
    await api.deployStage(path.pipelineId, path.source.id, path.target.id, items, note);
    for (let i = 0; i < 90; i++) {
      await sleep(i ? 5000 : 2000);
      const op = (await api.listDeployOperations(path.pipelineId)).find((o) => !before.has(o.id));
      if (op && ['Succeeded', 'Failed'].includes(op.status)) return { status: op.status, operationId: op.id };
    }
    return { status: 'Unknown' };
  }
}
