import failVerdict from '../demo/fail/verdict.json';
import failReview from '../demo/fail/model_review.json';
import failLoad from '../demo/fail/loadtest.json';
import failCapacity from '../demo/fail/capacity.json';
import failReport from '../demo/fail/report.md?raw';
import passVerdict from '../demo/pass/verdict.json';
import passReview from '../demo/pass/model_review.json';
import passLoad from '../demo/pass/loadtest.json';
import passCapacity from '../demo/pass/capacity.json';
import passReport from '../demo/pass/report.md?raw';
import { PHASES, type LaunchForm, type PhaseStatus, type PromotionPath } from './gate';
import type { Item, Report, Workspace } from './fabric';
import type { Account, GateService, LevelProgress, Progress, ScenarioFile } from './service';
import { inspectScenario, syntheticScenario } from './scenario';
import type { Capacity, Evidence, GateConfig, LoadTest, ModelReview, RunRecord, Verdict } from './types';

/**
 * Modo demo: datos SINTÉTICOS generados por tools/make_demo_evidence.py con el mismo paquete promotion_gate.
 * Un run nuevo recorre las cinco fases en ~45 s reales (comprimido: en Fabric dura de 30 a 60 min) y termina con el
 * veredicto PASS de la versión corregida del modelo.
 */
const WS_TEST = '7a1c0000-0000-4000-8000-0000000000a1';
const WS_PROD = '7a1c0000-0000-4000-8000-0000000000a2';
export const DEMO_DATASET_ID = '11111111-2222-3333-4444-555555555555';

const PHASE_SECONDS = [6, 14, 5, 8, 6, 5];

const fail: Evidence = { verdict: failVerdict as unknown as Verdict, review: failReview as ModelReview,
  loadtest: failLoad as unknown as LoadTest, capacity: failCapacity as Capacity, report: failReport };
const pass: Evidence = { verdict: passVerdict as unknown as Verdict, review: passReview as ModelReview,
  loadtest: passLoad as unknown as LoadTest, capacity: passCapacity as Capacity, report: passReport };

export const DEMO_HISTORY: RunRecord[] = [{
  run_id: 'GATE-20261104-0915-7C1E', user_id: 'demo', requested_by: 'lucia.martin@contoso.com',
  workspace_id: WS_TEST, workspace_name: 'Ventas [Test]', dataset_id: DEMO_DATASET_ID, dataset_name: 'Ventas',
  report_id: 'r-ventas', report_name: 'Ventas Dirección', model_key: 'Ventas',
  scenario_path: '/lakehouse/default/Files/PerfScenarios/Queries/ventas_direccion.json', scenario_source: 'upload',
  ramp_levels: '[6,20,60]', target_level: 60, pipeline_job_id: 'demo-job-fail', status: 'Completed',
  verdict: 'FAIL', promotable: false, started_at: '2026-11-04T09:15:00Z', finished_at: '2026-11-04T10:02:00Z',
}];

const START_KEY = 'promotion-gate.demo.started.v1';
const TOTAL_MS = PHASE_SECONDS.reduce((a, b) => a + b, 0) * 1000;
const startedAt = {
  all(): Record<string, number> {
    try { return JSON.parse(localStorage.getItem(START_KEY) ?? '{}'); } catch { return {}; }
  },
  get(id: string): number | undefined { return this.all()[id]; },
  has(id: string) { return this.get(id) !== undefined; },
  set(id: string, t: number) {
    try { localStorage.setItem(START_KEY, JSON.stringify({ ...this.all(), [id]: t })); } catch { /* sin persistencia */ }
  },
  delete(id: string) {
    const all = this.all(); delete all[id];
    try { localStorage.setItem(START_KEY, JSON.stringify(all)); } catch { /* sin persistencia */ }
  },
};

export class DemoGateService implements GateService {
  readonly demo = true;
  private signedIn = true;

  async account(): Promise<Account | null> {
    return this.signedIn ? { name: 'Usuario de demostración', username: 'demo@contoso.com' } : null;
  }

  async signIn() { this.signedIn = true; return this.account(); }

  async workspaces(): Promise<Workspace[]> {
    return [
      { id: '7a1c0000-0000-4000-8000-0000000000a0', displayName: 'Ventas [Dev]', capacityId: 'cap-dev' },
      { id: WS_TEST, displayName: 'Ventas [Test]', capacityId: 'cap-test' },
      { id: WS_PROD, displayName: 'Ventas', capacityId: 'cap-prod' },
      { id: '7a1c0000-0000-4000-8000-0000000000b1', displayName: 'Finanzas [Test]', capacityId: 'cap-test' },
    ];
  }

  async models(ws: string): Promise<Item[]> {
    if (ws === WS_TEST) return [
      { id: DEMO_DATASET_ID, displayName: 'Ventas', type: 'SemanticModel' },
      { id: '22222222-0000-4000-8000-000000000002', displayName: 'Ventas Objetivos', type: 'SemanticModel' },
    ];
    if (ws.endsWith('b1')) return [{ id: '33333333-0000-4000-8000-000000000003', displayName: 'Cuenta de resultados', type: 'SemanticModel' }];
    return [{ id: '44444444-0000-4000-8000-000000000004', displayName: 'Ventas', type: 'SemanticModel' }];
  }

  async reports(ws: string): Promise<Report[]> {
    if (ws !== WS_TEST) return [];
    return [
      { id: 'r-ventas', name: 'Ventas Dirección', datasetId: DEMO_DATASET_ID, webUrl: '#' },
      { id: 'r-ventas-tienda', name: 'Ventas Tiendas', datasetId: DEMO_DATASET_ID, webUrl: '#' },
      { id: 'r-objetivos', name: 'Seguimiento de objetivos', datasetId: '22222222-0000-4000-8000-000000000002', webUrl: '#' },
    ];
  }

  async capacityOf() { return '0f0f0f0f-1111-2222-3333-444444444444'; }

  async scenarios(): Promise<ScenarioFile[]> {
    return [
      { name: 'ventas_direccion.json', path: '/lakehouse/default/Files/PerfScenarios/Queries/ventas_direccion.json', sizeKb: 184, modified: '2026-11-04T08:51:00Z' },
      { name: 'objetivos.json', path: '/lakehouse/default/Files/PerfScenarios/Queries/objetivos.json', sizeKb: 96, modified: '2026-10-29T16:20:00Z' },
    ];
  }

  async uploadScenario(fileName: string, content: string) {
    inspectScenario(content);
    return `/lakehouse/default/Files/PerfScenarios/Queries/${fileName.replace(/[^A-Za-z0-9._-]+/g, '_')}`;
  }

  async synthesizeScenario(): Promise<string> {
    return syntheticScenario(
      [{ table: 'Hechos', name: 'Ventas' }, { table: 'Hechos', name: 'Margen %' }, { table: 'Hechos', name: 'Unidades' },
        { table: 'Hechos', name: 'Ticket medio' }],
      [{ table: 'Fecha', name: 'Mes', dataType: 'Text' }, { table: 'Tienda', name: 'Región', dataType: 'Text' },
        { table: 'Producto', name: 'Categoría', dataType: 'Text' }]);
  }

  async teamConfig(): Promise<Partial<GateConfig>> {
    return (passVerdict as unknown as Verdict).config;
  }

  async launch(form: LaunchForm) { startedAt.set(form.runId, Date.now()); }

  async locateJob(runId: string) {
    if (!startedAt.has(runId)) startedAt.set(runId, Date.now());
    return `demo-job-${runId}`;
  }

  async progress(jobId: string, runId: string): Promise<Progress> {
    if (jobId === 'demo-job-fail') return this.finished('Failed');
    const t0 = startedAt.get(runId) ?? Date.now() - 999_000;
    let elapsed = (Date.now() - t0) / 1000;
    const phases: PhaseStatus[] = PHASES.map((p, i) => {
      const dur = PHASE_SECONDS[i];
      const base = { id: p.id, label: p.label, detail: p.detail } as const;
      if (elapsed >= dur) { elapsed -= dur; return { ...base, state: 'done', durationMs: dur * 1000 }; }
      if (elapsed > 0) { elapsed = 0; return { ...base, state: 'running' }; }
      return { ...base, state: 'pending' };
    });
    const loadIdx = PHASES.findIndex((p) => p.id === 'load');
    const loadDone = phases[loadIdx].state === 'done';
    const loadElapsed = Math.max(0, (Date.now() - t0) / 1000 - PHASE_SECONDS[0]);
    const ramp = [6, 20, 60];
    const levels: LevelProgress[] = ramp
      .filter((_, i) => loadDone || loadElapsed > (i * PHASE_SECONDS[loadIdx]) / ramp.length)
      .map((level, i) => ({ level, done: loadDone || loadElapsed > ((i + 1) * PHASE_SECONDS[loadIdx]) / ramp.length }));
    const all = phases.every((p) => p.state === 'done');
    return { jobStatus: all ? 'Completed' : 'InProgress', phases, levels };
  }

  private finished(status: string): Progress {
    return {
      jobStatus: status,
      phases: PHASES.map((p) => ({ id: p.id, label: p.label, detail: p.detail, state: 'done' as const })),
      levels: [{ level: 6, done: true }, { level: 20, done: true }, { level: 60, done: true }],
    };
  }

  async evidence(runId: string): Promise<Evidence> {
    const old = runId === DEMO_HISTORY[0].run_id;
    const ev = old ? fail : pass;
    const t0 = startedAt.get(runId);
    const evaluated = old ? DEMO_HISTORY[0].finished_at! : new Date(t0 ? t0 + TOTAL_MS : Date.now()).toISOString();
    return { ...ev, verdict: ev.verdict && { ...ev.verdict, evaluated_utc: evaluated, context: { ...ev.verdict.context, run_id: runId } } };
  }

  async cancel(jobId: string) { startedAt.delete(jobId.replace('demo-job-', '')); }

  async promotionPath(workspaceId: string): Promise<PromotionPath | null> {
    if (workspaceId !== WS_TEST) return null;
    return {
      pipelineId: 'dp-ventas', pipelineName: 'Ventas',
      source: { id: 'st-test', displayName: 'Test', order: 1, workspaceId: WS_TEST, workspaceName: 'Ventas [Test]' },
      target: { id: 'st-prod', displayName: 'Producción', order: 2, workspaceId: WS_PROD, workspaceName: 'Ventas' },
    };
  }

  async promote() {
    await new Promise((r) => setTimeout(r, 2500));
    return { status: 'Succeeded', operationId: 'demo-op' };
  }
}
