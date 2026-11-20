import { describe, expect, it } from 'vitest';
import pipeline from '../../../pipelines/PL_PromotionGate.json';
import {
  activitiesMentionRun, candidateJobs, exitValue, gateOverride, makeRunId, modelKey, parseRamp, phaseStatuses,
  pipelineParams, promotionBlockers, promotionPath, rampProblems, rlsParams, verdictBlockReason, gateRejected, type LaunchForm,
} from './gate';
import type { ActivityRun } from './fabric';
import type { Verdict } from './types';

const form: LaunchForm = {
  runId: 'GATE-20261105-0930-4F2A', datasetName: 'Ventas', workspaceName: 'Ventas [Test]', modelKey: 'Ventas',
  queryfile: '/lakehouse/default/Files/PerfScenarios/Queries/ventas.json', rampLevels: [6, 20, 60], targetLevel: 60,
  sku: 'F64', iterations: 1, thinkTimes: true, thinkTimeScale: 1, rampUpSec: 30, rlsUsers: '', fullRun: true,
  capacityId: 'cap', capacityMetricsWorkspace: 'Capacity Metrics', toolingWorkspaceId: 'ws-tools', requestedBy: 'ana@contoso.com',
};

describe('identificadores', () => {
  it('genera números de certificado seguros para carpetas y prefijos', () => {
    const id = makeRunId(new Date('2026-11-05T09:30:12Z'), () => 0.5);
    expect(id).toBe('GATE-20261105-0930-7FFF');
    expect(id).toMatch(/^[A-Z0-9-]+$/);
  });

  it('deriva un model_key válido para el orquestador', () => {
    expect(modelKey('Cuenta de resultados (España)')).toBe('Cuenta_de_resultados_Espana');
    expect(modelKey('Ventas')).toBe('Ventas');
    expect(modelKey('***')).toBe('modelo');
    expect(modelKey('x'.repeat(80))).toHaveLength(40);
  });
});

describe('usuarios RLS', () => {
  it('una lista de UPN va a rls_users y una ruta a rls_users_file', () => {
    expect(rlsParams('')).toEqual({ rls_users: '', rls_users_file: '' });
    expect(rlsParams(' ana@contoso.com, luis@contoso.com ')).toEqual({ rls_users: 'ana@contoso.com, luis@contoso.com', rls_users_file: '' });
    expect(rlsParams('Files/PerfScenarios/Users/users.txt'))
      .toEqual({ rls_users: '', rls_users_file: '/lakehouse/default/Files/PerfScenarios/Users/users.txt' });
    expect(rlsParams('/lakehouse/default/Files/PerfScenarios/Users/ventas')).toEqual({
      rls_users: '', rls_users_file: '/lakehouse/default/Files/PerfScenarios/Users/ventas' });
  });

  it('el pipeline recibe ambos parámetros', () => {
    const p = pipelineParams({ ...form, rlsUsers: 'Files/PerfScenarios/Users/users.txt' });
    expect(p.rls_users).toBe('');
    expect(p.rls_users_file).toBe('/lakehouse/default/Files/PerfScenarios/Users/users.txt');
  });

  it('envía UPN terminados en .txt como lista global', () => {
    const p = pipelineParams({ ...form, rlsUsers: 'first@contoso.com, user@example.txt' });
    expect(p.rls_users).toBe('first@contoso.com, user@example.txt');
    expect(p.rls_users_file).toBe('');
  });

  it('envía un UPN terminado en .txt como lista del modelo', () => {
    const p = pipelineParams({ ...form, rlsModelUsers: 'other@example.txt' });
    expect(p.model_rls_settings).toEqual({ users: 'other@example.txt' });
    expect(p.model_rls_source).toBe('list');
  });

  it('conserva las rutas de archivos que contienen @', () => {
    const p = pipelineParams({ ...form, rlsUsers: '/lakehouse/default/Files/user@example.txt',
      rlsModelUsers: 'Files/Users/user@example.txt' });
    expect(p.rls_users_file).toBe('/lakehouse/default/Files/user@example.txt');
    expect(p.model_rls_settings).toEqual({ users_file: '/lakehouse/default/Files/Users/user@example.txt' });
    expect(p.model_rls_source).toBe('file');
    expect(rlsParams('Users/name@domain/users.txt').rls_users_file).toBe('Users/name@domain/users.txt');
    expect(rlsParams('users.txt').rls_users_file).toBe('users.txt');
  });

  it('envía lista global y lista específica del modelo sin mezclarlas', () => {
    const p = pipelineParams({ ...form, rlsUsers: 'global@contoso.com', rlsModelUsers: 'modelo@contoso.com' });
    expect(p.rls_users).toBe('global@contoso.com');
    expect(p.rls_users_file).toBe('');
    expect(p.model_rls_settings).toEqual({ users: 'modelo@contoso.com' });
    expect(p.model_rls_source).toBe('list');
  });

  it('envía archivos global y específico o solo el específico', () => {
    const p = pipelineParams({ ...form, rlsUsers: 'Files/Users/global.txt', rlsModelUsers: 'Files/Users/modelo.txt' });
    expect(p.rls_users_file).toBe('/lakehouse/default/Files/Users/global.txt');
    expect(p.model_rls_settings).toEqual({ users_file: '/lakehouse/default/Files/Users/modelo.txt' });
    expect(p.model_rls_source).toBe('file');
    expect(pipelineParams({ ...form, rlsModelUsers: 'Files/Users/modelo.txt' }).model_rls_settings)
      .toEqual({ users_file: '/lakehouse/default/Files/Users/modelo.txt' });
  });

  it('rechaza mezclar archivos y listas porque el origen es único por ejecución', () => {
    expect(() => pipelineParams({ ...form, rlsUsers: 'global@contoso.com', rlsModelUsers: 'Files/Users/modelo.txt' })).toThrow(/origen/i);
    expect(() => pipelineParams({ ...form, rlsUsers: 'Files/Users/global.txt', rlsModelUsers: 'modelo@contoso.com' })).toThrow(/origen/i);
  });

  it('rechaza UPN no válidos antes de lanzar', () => {
    expect(() => pipelineParams({ ...form, rlsModelUsers: 'no-es-un-upn' })).toThrow(/UPN/i);
  });
});

describe('rampa', () => {
  it('normaliza niveles', () => {
    expect(parseRamp('60, 6 20;20 abc -3')).toEqual([6, 20, 60]);
  });

  it('avisa de rampas que no sirven para el veredicto', () => {
    expect(rampProblems([6, 20], 60)[0]).toMatch(/no llega a los 60/);
    expect(rampProblems([400], 60).join()).toMatch(/300/);
    expect(rampProblems([6, 20, 60], 60)).toEqual([]);
  });
});

describe('parámetros del pipeline', () => {
  it('solo envía parámetros que PL_PromotionGate declara', () => {
    const declared = Object.keys(pipeline.properties.parameters);
    const sent = Object.keys(pipelineParams(form));
    expect(sent.filter((k) => !declared.includes(k))).toEqual([]);
    expect(sent).toEqual(expect.arrayContaining(['run_id', 'dataset', 'queryfile', 'ramp_levels', 'gate_config']));
  });

  it('el ajuste por run solo toca usuarios objetivo y SKU, nunca los SLO', () => {
    const o = gateOverride(form);
    expect(o).toEqual({ load_test: { target_level: 60 }, model_review: { sku: 'F64' } });
    expect(JSON.parse(pipelineParams(form).gate_config as string)).toEqual(o);
  });
});

const act = (activityName: string, status: string, extra: Partial<ActivityRun> = {}): ActivityRun =>
  ({ activityName, activityType: 'TridentNotebook', status, ...extra });

describe('fases', () => {
  it('traduce las actividades a fases y marca lo omitido al terminar', () => {
    const runs = [act('Set_RunId', 'Succeeded'), act('NB_Gate_ModelReview', 'Succeeded'), act('NB_Gate_Verdict', 'Succeeded')];
    const p = phaseStatuses(runs, 'Completed');
    expect(p.map((x) => x.state)).toEqual(['done', 'skipped', 'skipped', 'skipped', 'done']);
  });

  it('una fase en curso sigue en curso mientras el job corre', () => {
    const p = phaseStatuses([act('NB_Gate_ModelReview', 'Succeeded'), act('Run_LoadTest', 'InProgress')], 'InProgress');
    expect(p.slice(0, 3).map((x) => x.state)).toEqual(['done', 'running', 'pending']);
  });

  it('lee el exitValue JSON de un notebook', () => {
    const runs = [act('NB_Gate_Verdict', 'Succeeded', { output: { result: { exitValue: '{"verdict":"PASS","promotable":true}' } } })];
    expect(exitValue(runs, 'NB_Gate_Verdict')).toEqual({ verdict: 'PASS', promotable: true });
    expect(exitValue(runs, 'NB_Gate_ModelReview')).toBeNull();
  });
});

describe('localizar el job', () => {
  it('se queda con los jobs posteriores al lanzamiento, el más reciente primero', () => {
    const t = new Date('2026-11-05T09:30:00Z');
    const jobs = [
      { id: 'old', status: 'Completed', startTimeUtc: '2026-11-05T08:00:00' },
      { id: 'a', status: 'InProgress', startTimeUtc: '2026-11-05T09:30:05' },
      { id: 'b', status: 'InProgress', startTimeUtc: '2026-11-05T09:30:09Z' },
    ];
    expect(candidateJobs(jobs, t).map((j) => j.id)).toEqual(['b', 'a']);
  });

  it('reconoce el run por el run_id en la entrada de las actividades', () => {
    const runs = [act('NB_Gate_ModelReview', 'InProgress', { input: { parameters: { run_id: { value: 'GATE-X' } } } })];
    expect(activitiesMentionRun(runs, 'GATE-X')).toBe(true);
    expect(activitiesMentionRun(runs, 'GATE-Y')).toBe(false);
  });
});

describe('promoción', () => {
  const stages = [
    { id: 's0', displayName: 'Dev', order: 0, workspaceId: 'WS-DEV' },
    { id: 's1', displayName: 'Test', order: 1, workspaceId: 'ws-test' },
    { id: 's2', displayName: 'Producción', order: 2, workspaceId: 'ws-prod' },
  ];

  it('encuentra el stage del modelo y el siguiente', () => {
    const p = promotionPath('dp', 'Ventas', stages, 'WS-TEST');
    expect(p?.source.id).toBe('s1');
    expect(p?.target.id).toBe('s2');
    expect(promotionPath('dp', 'Ventas', stages, 'ws-prod')).toBeNull();
    expect(promotionPath('dp', 'Ventas', stages, 'otro')).toBeNull();
  });

  it('bloquea veredictos no promocionables, de otro modelo o ya promocionados', () => {
    const v = { verdict: 'PASS', promotable: true, context: { item_id: 'M1' }, checks: [{ status: 'PASS' }, { status: 'SKIP' }],
      config: { verdict: { warn_blocks_promotion: false } } } as unknown as Verdict;
    expect(promotionBlockers(v, 'm1')).toEqual([]);
    expect(promotionBlockers({ ...v, promotable: false, verdict: 'FAIL' }, 'm1')[0]).toMatch(/FAIL/);
    expect(promotionBlockers(v, 'm2')[0]).toMatch(/otro modelo/);
    expect(promotionBlockers(v, 'm1', '5 nov')[0]).toMatch(/ya se promocionó/);
    expect(promotionBlockers(null, 'm1')[0]).toMatch(/no ha emitido/);
  });

  it('distingue el rechazo del gate (Fail_Gate) de un fallo real del pipeline', () => {
    const ok = [act('NB_Gate_Verdict', 'Succeeded')];
    const rejected = [...ok, act('If_NotPromotable', 'Failed'), act('Fail_Gate', 'Failed')];
    expect(gateRejected(rejected)).toBe(true);
    expect(gateRejected([...rejected, act('If_ReviewAllowsLoadTest', 'Failed'), act('Run_LoadTest', 'Failed')])).toBe(false);
    expect(gateRejected([act('NB_Gate_ModelReview', 'Failed')])).toBe(false);
    expect(gateRejected(ok)).toBe(false);
  });

  it('no se fía de promotable si no cuadra con el veredicto ni con las comprobaciones', () => {
    const v = { verdict: 'PASS', promotable: true, context: {}, checks: [{ status: 'PASS' }],
      config: { verdict: { warn_blocks_promotion: false } } } as unknown as Verdict;
    expect(verdictBlockReason(v)).toBeNull();
    expect(verdictBlockReason({ ...v, verdict: 'FAIL' })).toMatch(/incompatible/);
    expect(verdictBlockReason({ ...v, checks: [{ status: 'FAIL' }] } as unknown as Verdict)).toMatch(/dan FAIL/);
    const warn = { ...v, verdict: 'WARN', checks: [{ status: 'WARN' }] } as unknown as Verdict;
    expect(verdictBlockReason(warn)).toBeNull();
    expect(verdictBlockReason({ ...warn, config: { verdict: { warn_blocks_promotion: true } } } as unknown as Verdict)).toMatch(/WARN/);
  });
});
