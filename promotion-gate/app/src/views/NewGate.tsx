import { ExternalLink, FileJson, FlaskConical, Info, Rocket, TriangleAlert, Upload } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { env } from '../lib/env';
import type { Item, Report, Workspace } from '../lib/fabric';
import { makeRunId, modelKey, rampProblems, type LaunchForm } from '../lib/gate';
import { inspectScenario, type ScenarioSummary } from '../lib/scenario';
import type { ScenarioFile } from '../lib/service';
import { useGate } from '../lib/store';
import type { GateConfig } from '../lib/types';
import { num } from '../lib/format';
import { grantAccess, SignInRequiredError } from '../lib/msal';

const LEVELS = [1, 5, 6, 10, 20, 40, 60, 100, 150, 200, 300];
const SKUS = ['F2', 'F4', 'F8', 'F16', 'F32', 'F64', 'F128', 'F256', 'F512', 'F1024', 'F2048'];

type Source = 'upload' | 'existing' | 'synthetic';

interface Loaded<T> { data: T; loading: boolean; error: string | null }
const idle = <T,>(data: T): Loaded<T> => ({ data, loading: false, error: null });

function useLoad<T>(fn: (() => Promise<T>) | null, initial: T, deps: unknown[]): Loaded<T> {
  const [s, set] = useState<Loaded<T>>(idle(initial));
  useEffect(() => {
    if (!fn) { set(idle(initial)); return; }
    let alive = true;
    set((p) => ({ ...p, loading: true, error: null }));
    fn().then((data) => alive && set({ data, loading: false, error: null }))
      .catch((e: Error) => alive && set({ data: initial, loading: false, error: e.message }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return s;
}

export function NewGate() {
  const { service, account, signIn, addRun, go, missing } = useGate();
  const signedIn = !!account;

  const workspaces = useLoad<Workspace[]>(signedIn ? () => service.workspaces() : null, [], [signedIn]);
  const [wsId, setWsId] = useState('');
  const ws = workspaces.data.find((w) => w.id === wsId);
  const models = useLoad<Item[]>(wsId ? () => service.models(wsId) : null, [], [wsId]);
  const reports = useLoad<Report[]>(wsId ? () => service.reports(wsId) : null, [], [wsId]);
  const [modelId, setModelId] = useState('');
  const model = models.data.find((m) => m.id === modelId);
  const modelReports = useMemo(() => reports.data.filter((r) => r.datasetId?.toLowerCase() === modelId.toLowerCase()), [reports.data, modelId]);
  const [reportId, setReportId] = useState('');
  const report = modelReports.find((r) => r.id === reportId);

  const [source, setSource] = useState<Source>('upload');
  const [upload, setUpload] = useState<{ name: string; text: string; summary: ScenarioSummary } | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [consent, setConsent] = useState({ tick: 0, busy: false, error: null as string | null });
  const existing = useLoad<ScenarioFile[]>(signedIn ? () => service.scenarios() : null, [], [signedIn, consent.tick]);
  const [existingPath, setExistingPath] = useState('');
  const [synthetic, setSynthetic] = useState<{ text: string; summary: ScenarioSummary } | null>(null);
  const [synthState, setSynthState] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null });
  const fileRef = useRef<HTMLInputElement>(null);

  const team = useLoad<Partial<GateConfig> | null>(signedIn ? () => service.teamConfig() : null, null, [signedIn, consent.tick]);
  const needsConsent = !env.demo && !!team.error && /consentimiento/i.test(team.error);
  const grant = async () => {
    setConsent((c) => ({ ...c, busy: true, error: null }));
    try {
      await grantAccess();
      setConsent((c) => ({ tick: c.tick + 1, busy: false, error: null }));
    } catch (e) {
      setConsent((c) => ({ ...c, busy: false, error: e instanceof SignInRequiredError ? null : (e as Error).message }));
    }
  };
  const [target, setTarget] = useState(60);
  const [ramp, setRamp] = useState<number[]>([6, 20, 60]);
  const [sku, setSku] = useState('F64');
  const [thinkTimes, setThinkTimes] = useState(true);
  const [iterations, setIterations] = useState(1);
  const [rampUp, setRampUp] = useState(30);
  const [rls, setRls] = useState('');
  const [fullRun, setFullRun] = useState(true);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);

  useEffect(() => {
    const t = team.data?.load_test?.target_level;
    const s = team.data?.model_review?.sku;
    if (t) setTarget(t);
    if (s) setSku(s);
  }, [team.data]);

  useEffect(() => { setModelId(''); setReportId(''); }, [wsId]);
  useEffect(() => { setReportId(modelReports.length === 1 ? modelReports[0].id : ''); setSynthetic(null); }, [modelId, modelReports.length]);

  const onFile = async (f: File | undefined) => {
    setUploadError(null);
    setUpload(null);
    if (!f) return;
    try {
      const text = await f.text();
      setUpload({ name: f.name, text, summary: inspectScenario(text) });
    } catch (e) {
      setUploadError((e as Error).message);
    }
  };

  const generate = async () => {
    if (!model) return;
    setSynthState({ busy: true, error: null });
    try {
      const text = await service.synthesizeScenario(model.id);
      setSynthetic({ text, summary: inspectScenario(text) });
      setSynthState({ busy: false, error: null });
    } catch (e) {
      setSynthState({ busy: false, error: (e as Error).message });
    }
  };

  const scenarioReady = source === 'upload' ? !!upload : source === 'existing' ? !!existingPath : !!synthetic;
  const scenarioSummary = source === 'upload' ? upload?.summary : source === 'synthetic' ? synthetic?.summary : undefined;
  const problems = rampProblems(ramp, target);
  const blocking = ramp.length === 0 || ramp.some((l) => l > 300);
  const canLaunch = signedIn && !!model && !!ws && scenarioReady && !blocking && !launching && missing.length === 0;

  const plan = useMemo(() => {
    const scenario = Math.max(1, (scenarioSummary?.durationSec ?? 120) / 60) * iterations;
    const load = Math.round(ramp.length * (3 + scenario + rampUp / 60));
    return [
      ['Buenas prácticas', 'BPA y VertiPaq del modelo', 2],
      ['Test de carga', `${ramp.length} niveles, de ${ramp[0] ?? '–'} a ${ramp[ramp.length - 1] ?? '–'} usuarios`, load],
      ['Informe de carga', 'Percentiles, errores y visuales lentas', 2],
      ['Capacity Metrics', 'Espera a que lleguen las métricas (sondeo cada 2 min) y lee utilización y throttling', 8],
      ['Veredicto', 'Certificado, informe y auditoría Delta', 2],
    ] as [string, string, number][];
  }, [ramp, scenarioSummary, iterations, rampUp]);
  const minutes = plan.reduce((s, p) => s + p[2], 0);

  const toggleLevel = (l: number) => setRamp((r) => (r.includes(l) ? r.filter((x) => x !== l) : [...r, l].sort((a, b) => a - b)));

  const launch = async () => {
    if (!model || !ws || !account) return;
    setLaunching(true);
    setLaunchError(null);
    const runId = makeRunId();
    const key = modelKey(model.displayName);
    try {
      let queryfile = existingPath;
      if (source === 'upload' && upload) queryfile = await service.uploadScenario(`${key}_${runId}.json`, upload.text);
      if (source === 'synthetic' && synthetic) queryfile = await service.uploadScenario(`${key}_${runId}_sintetico.json`, synthetic.text);
      const capacityId = await service.capacityOf(ws.id).catch(() => undefined);
      const form: LaunchForm = {
        runId, datasetName: model.displayName, workspaceName: ws.displayName, modelKey: key, queryfile,
        rampLevels: ramp, targetLevel: target, sku, iterations, thinkTimes, thinkTimeScale: 1, rampUpSec: rampUp,
        rlsUsers: rls, fullRun, capacityId, capacityMetricsWorkspace: env.capacityMetricsWorkspace, toolingWorkspaceId: env.gateWorkspaceId,
        requestedBy: account.username,
      };
      const startedAt = new Date().toISOString();
      await service.launch(form);
      await addRun({
        run_id: runId, user_id: account.username, requested_by: account.username, workspace_id: ws.id, workspace_name: ws.displayName,
        dataset_id: model.id, dataset_name: model.displayName, report_id: report?.id, report_name: report?.name, model_key: key,
        scenario_path: queryfile, scenario_source: source, ramp_levels: JSON.stringify(ramp), target_level: target,
        gate_config_json: JSON.stringify({ load_test: { target_level: target }, model_review: { sku } }),
        pipeline_job_id: '', status: 'Locating', started_at: startedAt,
      });
      go({ name: 'run', runId });
    } catch (e) {
      setLaunchError((e as Error).message);
    } finally {
      setLaunching(false);
    }
  };

  const lt = team.data?.load_test;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Nuevo gate de promoción</h1>
          <p>Elige el modelo que quieres llevar a producción y cómo navegan sus usuarios. El gate revisa buenas prácticas, lo somete a carga, lee Capacity Metrics y emite el certificado.</p>
        </div>
      </header>

      {missing.length > 0 && (
        <div className="notice notice--warn" style={{ marginBottom: 'var(--sp-5)' }}>
          <TriangleAlert aria-hidden />
          <div><strong>Falta configuración de la app</strong><p>Define {missing.join(', ')} en el .env de la app y vuelve a desplegar. Mientras tanto puedes explorar con <code>npm run dev:demo</code>.</p></div>
        </div>
      )}

      <div className="sheet">
        <div className="blocks">
          <section className="block" data-state={model ? 'done' : 'active'} aria-labelledby="b1">
            <div className="block__no" aria-hidden>1</div>
            <div className="block__body">
              <div className="block__title">
                <div><h2 id="b1">Modelo semántico</h2><p>El modelo en el stage de test, el que se promocionará si el veredicto lo permite.</p></div>
                {!signedIn && <button className="btn btn--primary" onClick={signIn}>Iniciar sesión en Fabric</button>}
              </div>
              <div className="grid-3">
                <label className="field">
                  <span className="label">Workspace</span>
                  <select className="select" value={wsId} onChange={(e) => setWsId(e.target.value)} disabled={!signedIn || workspaces.loading}>
                    <option value="">{workspaces.loading ? 'Cargando workspaces…' : 'Selecciona un workspace'}</option>
                    {workspaces.data.map((w) => <option key={w.id} value={w.id}>{w.displayName}</option>)}
                  </select>
                  {workspaces.error && <span className="field__error">{workspaces.error}</span>}
                </label>
                <label className="field">
                  <span className="label">Modelo semántico</span>
                  <select className="select" value={modelId} onChange={(e) => setModelId(e.target.value)} disabled={!wsId || models.loading}>
                    <option value="">{models.loading ? 'Cargando modelos…' : models.data.length || !wsId ? 'Selecciona un modelo' : 'Este workspace no tiene modelos'}</option>
                    {models.data.map((m) => <option key={m.id} value={m.id}>{m.displayName}</option>)}
                  </select>
                  {models.error && <span className="field__error">{models.error}</span>}
                </label>
                <label className="field">
                  <span className="label">Informe (opcional)</span>
                  <select className="select" value={reportId} onChange={(e) => setReportId(e.target.value)} disabled={!modelId || reports.loading}>
                    <option value="">{modelReports.length ? 'Sin informe' : 'Ningún informe usa este modelo'}</option>
                    {modelReports.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                  <span className="field__hint">Se promociona junto al modelo y es el que grabas en Performance Analyzer.</span>
                </label>
              </div>
            </div>
          </section>

          <section className="block" data-state={scenarioReady ? 'done' : model ? 'active' : undefined} aria-labelledby="b2">
            <div className="block__no" aria-hidden>2</div>
            <div className="block__body">
              <div className="block__title">
                <div><h2 id="b2">Escenario de navegación</h2><p>Lo que hace cada usuario virtual: las consultas DAX de los visuales y las pausas entre clics.</p></div>
                {report?.webUrl && report.webUrl !== '#' && (
                  <a className="btn btn--quiet" href={report.webUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden />Abrir informe</a>
                )}
              </div>
              <div className="choices" role="radiogroup" aria-label="Origen del escenario">
                <label className="choice">
                  <input type="radio" name="src" checked={source === 'upload'} onChange={() => setSource('upload')} />
                  <div>
                    <strong>Subir una grabación de Performance Analyzer</strong>
                    <span>Power BI Desktop, Ver, Performance Analyzer, Iniciar grabación, navega como un usuario y Exportar. Es la opción más fiel.</span>
                    {source === 'upload' && (
                      <div className="row" style={{ marginTop: 'var(--sp-3)' }}>
                        <input ref={fileRef} type="file" accept=".json,application/json" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
                        <button type="button" className="btn" onClick={() => fileRef.current?.click()}><Upload size={16} aria-hidden />Elegir fichero JSON</button>
                        {upload && <span className="field__hint"><FileJson size={14} aria-hidden /> {upload.name}: {upload.summary.actions} acciones, {upload.summary.queries} consultas, {upload.summary.visuals} visuales, {Math.round(upload.summary.durationSec / 60)} min de navegación</span>}
                        {uploadError && <span className="field__error">{uploadError}</span>}
                      </div>
                    )}
                  </div>
                </label>
                <label className="choice">
                  <input type="radio" name="src" checked={source === 'existing'} onChange={() => setSource('existing')} />
                  <div>
                    <strong>Reutilizar un escenario ya subido</strong>
                    <span>Los ficheros de Files/PerfScenarios/Queries del lakehouse del gate.</span>
                    {source === 'existing' && (
                      <select className="select" style={{ marginTop: 'var(--sp-3)', maxWidth: 520 }} value={existingPath} onChange={(e) => setExistingPath(e.target.value)}>
                        <option value="">{existing.loading ? 'Cargando…' : existing.data.length ? 'Selecciona un escenario' : 'No hay escenarios subidos'}</option>
                        {existing.data.map((f) => <option key={f.path} value={f.path}>{f.name} ({f.sizeKb} KB)</option>)}
                      </select>
                    )}
                  </div>
                </label>
                <label className="choice">
                  <input type="radio" name="src" checked={source === 'synthetic'} onChange={() => setSource('synthetic')} />
                  <div>
                    <strong>Generar un escenario sintético desde el modelo</strong>
                    <span>Tarjetas y desgloses con las medidas visibles del modelo. Útil para un primer run; no refleja cómo navegan tus usuarios.</span>
                    {source === 'synthetic' && (
                      <div className="row" style={{ marginTop: 'var(--sp-3)' }}>
                        <button type="button" className="btn" onClick={generate} disabled={!model || synthState.busy}>
                          <FlaskConical size={16} aria-hidden />{synthState.busy ? 'Leyendo el modelo…' : synthetic ? 'Volver a generar' : 'Generar escenario'}
                        </button>
                        {!model && <span className="field__hint">Elige antes un modelo.</span>}
                        {synthetic && <span className="field__hint">{synthetic.summary.actions} páginas, {synthetic.summary.queries} consultas</span>}
                        {synthState.error && <span className="field__error">{synthState.error}</span>}
                      </div>
                    )}
                  </div>
                </label>
              </div>
            </div>
          </section>

          <section className="block" data-state={model && scenarioReady ? 'active' : undefined} aria-labelledby="b3">
            <div className="block__no" aria-hidden>3</div>
            <div className="block__body">
              <div className="block__title">
                <div><h2 id="b3">Carga y objetivo de producción</h2><p>Cuántos usuarios simultáneos tendrá el modelo en producción y en qué capacidad vivirá.</p></div>
              </div>
              <div className="grid-4">
                <label className="field">
                  <span className="label">Usuarios objetivo</span>
                  <input className="input num" type="number" min={1} max={300} value={target} onChange={(e) => setTarget(Math.max(1, Number(e.target.value) || 1))} />
                </label>
                <label className="field">
                  <span className="label">SKU de producción</span>
                  <select className="select" value={sku} onChange={(e) => setSku(e.target.value)}>{SKUS.map((s) => <option key={s}>{s}</option>)}</select>
                </label>
                <label className="field">
                  <span className="label">Iteraciones por usuario</span>
                  <input className="input num" type="number" min={1} max={10} value={iterations} onChange={(e) => setIterations(Math.min(10, Math.max(1, Number(e.target.value) || 1)))} />
                </label>
                <label className="field">
                  <span className="label">Arranque escalonado (s)</span>
                  <input className="input num" type="number" min={0} max={600} value={rampUp} onChange={(e) => setRampUp(Math.max(0, Number(e.target.value) || 0))} />
                </label>
              </div>

              <div className="field" style={{ marginTop: 'var(--sp-5)' }}>
                <span className="label" id="ramp-l">Rampa de usuarios concurrentes</span>
                <div className="ramp" role="group" aria-labelledby="ramp-l">
                  {LEVELS.map((l) => <button key={l} type="button" aria-pressed={ramp.includes(l)} onClick={() => toggleLevel(l)}>{l}</button>)}
                </div>
                <span className="field__hint">Cada nivel se ejecuta después del anterior. Seleccionados: {ramp.length ? ramp.join(', ') : 'ninguno'}.</span>
              </div>
              {problems.length > 0 && (
                <div className="notice notice--warn" style={{ marginTop: 'var(--sp-3)' }}>
                  <TriangleAlert aria-hidden /><div>{problems.map((p) => <p key={p}>{p}</p>)}</div>
                </div>
              )}

              <div className="grid-2" style={{ marginTop: 'var(--sp-5)' }}>
                <div className="field">
                  <span className="label">Ritmo de los usuarios</span>
                  <label className="switch"><input type="checkbox" checked={thinkTimes} onChange={(e) => setThinkTimes(e.target.checked)} />Reproducir las pausas grabadas entre clics</label>
                  <span className="field__hint">Sin pausas es una prueba de estrés: útil para buscar el límite, no para el veredicto.</span>
                  <label className="switch" style={{ marginTop: 'var(--sp-3)' }}><input type="checkbox" checked={fullRun} onChange={(e) => setFullRun(e.target.checked)} />Completar carga y Capacity Metrics aunque fallen las buenas prácticas</label>
                  <span className="field__hint">{fullRun ? 'El certificado incluirá todas las fases aunque el modelo ya no sea apto.' : 'Si las buenas prácticas fallan, el gate se detiene y ahorra capacidad.'}</span>
                </div>
                <label className="field">
                  <span className="label">Usuarios RLS (opcional)</span>
                  <input className="input" placeholder="usuario1@empresa.com, usuario2@empresa.com  o  Files/PerfScenarios/Users/users.txt" value={rls} onChange={(e) => setRls(e.target.value)} />
                  <span className="field__hint">UPN separados por comas, o la ruta de un fichero del lakehouse del gate con un UPN por línea. Se reparten entre los usuarios virtuales y necesitan permiso de lectura y build.</span>
                </label>
              </div>

              <div className="notice" style={{ marginTop: 'var(--sp-5)' }}>
                <Info aria-hidden />
                <div>
                  <strong>Umbrales del equipo (gate.yaml)</strong>
                  {lt ? <p>p95 ≤ {num(lt.p95_sec, 1)} s, p50 ≤ {num(lt.p50_sec, 1)} s, errores ≤ {num((lt.max_error_rate ?? 0) * 100, 0)} %, degradación del p95 ≤ ×{num(lt.max_p95_growth_ratio, 1)}. Se cambian por PR en el repositorio, no desde aquí.</p>
                    : needsConsent
                      ? <>
                          <p>Falta tu permiso para leer OneLake y Power BI desde la app.</p>
                          <button type="button" className="btn" style={{ marginTop: 'var(--sp-2)' }} onClick={grant} disabled={consent.busy}>
                            {consent.busy ? 'Esperando al inicio de sesión…' : 'Dar acceso'}
                          </button>
                          {consent.error && <p role="alert">{consent.error}</p>}
                        </>
                      : <p>{team.loading ? 'Leyendo gate.yaml…' : `No se ha podido leer gate.yaml; el gate usará los valores por defecto.${team.error ? ` (${team.error})` : ''}`}</p>}
                </div>
              </div>
            </div>
          </section>

          <section className="block" aria-labelledby="b4">
            <div className="block__no" aria-hidden>4</div>
            <div className="block__body">
              <div className="block__title"><div><h2 id="b4">Lanzamiento</h2><p>El gate corre en Fabric aunque cierres la app. Recibirás el certificado en «Runs».</p></div></div>
              <ol className="plan" aria-label="Fases del gate y duración estimada">
                {plan.map(([name, detail, m]) => (
                  <li key={name}><b>{name}</b><span>{detail}</span><span className="num">~{m} min</span></li>
                ))}
              </ol>
              {launchError && <div className="notice notice--fail" style={{ marginBottom: 'var(--sp-4)' }}><TriangleAlert aria-hidden /><div><strong>No se ha podido lanzar el gate</strong><p>{launchError}</p></div></div>}
            </div>
          </section>
        </div>
        <div className="summary-bar">
          <p>
            {model ? <><b>{model.displayName}</b> en {ws?.displayName}</> : 'Sin modelo'}{', '}
            rampa <b className="num">{ramp.join(' → ') || '–'}</b> usuarios, objetivo <b className="num">{target}</b>, {sku}.{' '}
            Duración estimada <b className="num">~{minutes} min</b>.
          </p>
          <button className="btn btn--primary btn--lg" onClick={launch} disabled={!canLaunch}>
            <Rocket size={18} aria-hidden />{launching ? 'Lanzando…' : 'Lanzar gate'}
          </button>
        </div>
      </div>
    </>
  );
}
