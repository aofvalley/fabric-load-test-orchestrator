import { ArrowDownToLine, ArrowRight, ExternalLink, FileText, OctagonX, PenLine, ShieldCheck, TriangleAlert } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { LatencyChart } from '../components/LatencyChart';
import { PhaseRoute } from '../components/PhaseRoute';
import { ReleaseTag } from '../components/ReleaseTag';
import { StatusTag } from '../components/StatusTag';
import { AREA_LABEL, dateTime, duration, num, pct, secs } from '../lib/format';
import { PHASES, promotionBlockers, type PhaseStatus, type PromotionPath } from '../lib/gate';
import { ACTIVE, useGate } from '../lib/store';
import type { Advice, Area, Capacity, Check, Evidence, LoadTest, ModelReview, RunRecord, Status } from '../lib/types';

type Tab = 'summary' | 'advice' | 'load' | 'model' | 'capacity' | 'report';

const RANK: Record<Status, number> = { FAIL: 0, WARN: 1, SKIP: 2, PASS: 3 };

const TABS = (advice: number): [Tab, string][] => [['summary', 'Comprobaciones'], ['advice', `Mejoras (${advice})`], ['load', 'Test de carga'],
  ['model', 'Buenas prácticas'], ['capacity', 'Capacity Metrics'], ['report', 'Informe']];

function SignatureBox({ run, name, when, blank }: { run: RunRecord; name?: string; when?: string; blank?: string }) {
  return (
    <dl className="signoff__line">
      <div><dt>Referencia del certificado</dt><dd className="num">{run.run_id}</dd></div>
      <div className="wide"><dt>Firma de autorización</dt><dd className={name ? 'sig' : 'blank'}>{name ?? blank}</dd></div>
      <div><dt>Fecha</dt><dd className="num">{when ?? '–'}</dd></div>
    </dl>
  );
}

function LockedSignOff({ run }: { run: RunRecord }) {
  return (
    <section className="sheet signoff" aria-label="Promoción">
      <h3><PenLine size={18} aria-hidden />Autorización de puesta en servicio</h3>
      <SignatureBox run={run} blank="La firma se habilita cuando el certificado sea apto" />
    </section>
  );
}

export function RunView({ runId }: { runId: string }) {
  const { runs, live, evidence, loadEvidence, go, service, patchRun } = useGate();
  const run = runs.find((r) => r.run_id === runId);
  const ev = evidence[runId];
  const [tab, setTab] = useState<Tab>('summary');
  const active = run ? ACTIVE.includes(run.status) : false;

  useEffect(() => {
    if (run && !active) void loadEvidence(runId);
  }, [runId, active, run, loadEvidence]);

  if (!run) {
    return (
      <div className="sheet empty">
        <h2>No encuentro el run {runId}</h2>
        <p>Puede que se lanzara desde otro navegador sin historial compartido. Busca su veredicto en Files/PromotionGate/runs del lakehouse del gate.</p>
        <button className="btn" onClick={() => go({ name: 'runs' })}>Ver todos los runs</button>
      </div>
    );
  }

  const l = live[runId];
  const phases: PhaseStatus[] = l?.phases ?? PHASES.map((p) => ({
    id: p.id, label: p.label, detail: p.detail,
    state: active ? 'pending' : run.status === 'Completed' || ev?.verdict ? 'done' : 'skipped',
  }));
  const running = phases.find((p) => p.state === 'running');
  const verdict = ev?.verdict ?? null;

  const cancel = async () => {
    if (!run.pipeline_job_id) return;
    await service.cancel(run.pipeline_job_id).catch(() => undefined);
    await patchRun(runId, { status: 'Cancelled', finished_at: new Date().toISOString() });
  };

  const download = () => {
    if (!ev?.report) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([ev.report], { type: 'text/markdown' }));
    a.download = `${runId}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <header className="run-head">
        <div>
          <div className="run-head__no">{run.run_id}</div>
          <div className="run-head__meta">
            <span>Modelo <b>{run.dataset_name}</b></span>
            <span>Workspace <b>{run.workspace_name}</b></span>
            {run.report_name && <span>Informe <b>{run.report_name}</b></span>}
            <span>Lanzado por <b>{run.requested_by}</b>, {dateTime(run.started_at)}</span>
            <span>Duración <b className="num">{duration(run.started_at, run.finished_at)}</b></span>
          </div>
        </div>
        <div className="row">
          {active && <button className="btn btn--danger" onClick={cancel} disabled={!run.pipeline_job_id}><OctagonX size={16} aria-hidden />Cancelar run</button>}
          {ev?.report && <button className="btn" onClick={download}><ArrowDownToLine size={16} aria-hidden />Descargar informe</button>}
        </div>
      </header>

      <div className="run-grid">
        <div className="stack">
          <section className="sheet" aria-label="Progreso del gate">
            <PhaseRoute phases={phases} levels={l?.levels ?? []} />
            {active && (
              <div className="summary-bar">
                <p>{run.status === 'Locating' ? 'Esperando a que Fabric arranque el pipeline…' : <>En curso: <b>{running?.label ?? 'preparando'}</b>. Puedes cerrar la app; el gate sigue en Fabric.</>}</p>
              </div>
            )}
            {l?.failure && <div className="notice notice--fail" style={{ margin: 'var(--sp-4) var(--sp-5)' }}><TriangleAlert aria-hidden /><div><strong>El pipeline ha fallado</strong><p>{l.failure}</p></div></div>}
          </section>

          {!active && !verdict && (
            <div className="sheet empty">
              <h2>{run.status === 'Cancelled' ? 'Run cancelado' : 'Sin certificado'}</h2>
              <p>{run.status === 'Cancelled' ? 'Se canceló antes de emitir el veredicto. Lanza un gate nuevo cuando quieras.'
                : 'El gate terminó sin escribir verdict.json. Revisa el run del pipeline PL_PromotionGate en Fabric; puedes repetir solo las fases que faltan con smgate run-item.'}</p>
            </div>
          )}

          {verdict && ev && (
            <section className="sheet">
              <div className="tabs" role="tablist" aria-label="Evidencias">
                {TABS(verdict.advice.length).map(([id, label], i, all) => (
                  <button key={id} role="tab" aria-selected={tab === id} aria-controls={`p-${id}`} id={`t-${id}`} tabIndex={tab === id ? 0 : -1}
                    onClick={() => setTab(id)}
                    onKeyDown={(e) => {
                      const k = e.key;
                      const next = k === 'ArrowRight' ? (i + 1) % all.length : k === 'ArrowLeft' ? (i - 1 + all.length) % all.length
                        : k === 'Home' ? 0 : k === 'End' ? all.length - 1 : -1;
                      if (next < 0) return;
                      e.preventDefault();
                      setTab(all[next][0]);
                      document.getElementById(`t-${all[next][0]}`)?.focus();
                    }}>{label}</button>
                ))}
              </div>
              <div className="tab-panel" role="tabpanel" id={`p-${tab}`} aria-labelledby={`t-${tab}`}>
                {tab === 'summary' && <Checks checks={verdict.checks} />}
                {tab === 'advice' && <AdviceList advice={verdict.advice} />}
                {tab === 'load' && <LoadPanel load={ev.loadtest} target={verdict.config.load_test.target_level} slo={verdict.config.load_test.p95_sec} />}
                {tab === 'model' && <ModelPanel review={ev.review} sku={verdict.config.model_review.sku} />}
                {tab === 'capacity' && <CapacityPanel cap={ev.capacity} cfg={verdict.config.capacity} />}
                {tab === 'report' && <div className="report"><pre>{ev.report ?? 'Sin report.md'}</pre></div>}
              </div>
            </section>
          )}
        </div>

        <aside className="run-aside">
          <ReleaseTag runId={run.run_id} dataset={run.dataset_name} workspace={run.workspace_name} verdict={active ? null : verdict} runningPhase={running?.label} />
          {verdict && !active ? <SignOff run={run} ev={ev} /> : <LockedSignOff run={run} />}
        </aside>
      </div>
    </>
  );
}

// ---------------- Comprobaciones ----------------
function Checks({ checks }: { checks: Check[] }) {
  const byArea = (['model_review', 'load_test', 'capacity'] as Area[]).map((a) => ({
    area: a, items: checks.filter((c) => c.area === a).sort((x, y) => RANK[x.status] - RANK[y.status]),
  }));
  return (
    <div className="areas">
      {byArea.map(({ area, items }) => (
        <section className="area" key={area} aria-labelledby={`a-${area}`}>
          <h3 id={`a-${area}`}>{AREA_LABEL[area]}</h3>
          <ul className="checks">
            {items.map((c) => (
              <li key={c.id}><div><StatusTag status={c.status} /></div><div><b>{c.title}</b><span>{c.detail}</span></div></li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

// ---------------- Mejoras ----------------
function AdviceList({ advice }: { advice: Advice[] }) {
  const [area, setArea] = useState<Area | 'all'>('all');
  const shown = advice.filter((a) => area === 'all' || a.area === area);
  if (!advice.length) return <p>Ninguna regla de mejora ha saltado en este run.</p>;
  return (
    <>
      <div className="filters" role="group" aria-label="Filtrar por área">
        {(['all', 'model_review', 'load_test', 'capacity'] as const).map((a) => (
          <button key={a} aria-pressed={area === a} onClick={() => setArea(a)}>
            {a === 'all' ? `Todas (${advice.length})` : `${AREA_LABEL[a]} (${advice.filter((x) => x.area === a).length})`}
          </button>
        ))}
      </div>
      <ol className="advice">
        {shown.map((a) => (
          <li key={a.title}>
            <span className="mag" data-p={a.priority} title={`Prioridad ${a.priority === 1 ? 'alta' : a.priority === 2 ? 'media' : 'baja'}`}><i /></span>
            <div>
              <h4>{a.title}</h4>
              <p>{a.action}</p>
              {a.evidence && <div className="ev">Dato: <b>{a.evidence}</b></div>}
              <div className="meta">
                <span>Prioridad {a.priority === 1 ? 'alta' : a.priority === 2 ? 'media' : 'baja'}</span>
                <span>{AREA_LABEL[a.area]}</span>
                {a.reference && <a href={a.reference} target="_blank" rel="noreferrer">Documentación <ExternalLink size={12} aria-hidden /></a>}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}

// ---------------- Test de carga ----------------
function LoadPanel({ load, target, slo }: { load: LoadTest | null; target: number; slo: number }) {
  if (!load || !load.models?.length) return <p>No hay resultados del test de carga{load?.error ? `: ${load.error}` : '.'}</p>;
  return (
    <>
      {load.models.map((m) => {
        const measured = m.levels.filter((x) => x.queries);
        const atTarget = measured.find((x) => x.level === target) ?? measured.filter((x) => x.level <= target).pop() ?? measured[measured.length - 1];
        let sustained = 0;
        for (const lv of [...m.levels].sort((a, b) => a.level - b.level)) {
          if (lv.queries && (lv.p95 ?? Infinity) <= slo && lv.error_rate <= 0.01) sustained = lv.level; else break;
        }
        const failed = m.levels.reduce((s, x) => s + x.failed_queries, 0);
        const expected = m.levels.reduce((s, x) => s + x.expected_queries, 0) || 1;
        return (
          <div key={m.model_key}>
            <dl className="kv">
              <div><dt>Nivel sostenido</dt><dd data-s={sustained >= target ? 'PASS' : 'FAIL'}>{sustained} <small>de {target} usuarios</small></dd></div>
              <div><dt>p95 con {atTarget?.level ?? '–'} usuarios</dt><dd data-s={(atTarget?.p95 ?? 0) > slo ? 'FAIL' : 'PASS'}>{secs(atTarget?.p95)}</dd></div>
              <div><dt>Consultas fallidas</dt><dd data-s={failed / expected > 0.01 ? 'FAIL' : 'PASS'}>{pct((100 * failed) / expected, 1)} <small>{failed} de {expected}</small></dd></div>
              <div><dt>Rendimiento máx.</dt><dd>{num(Math.max(...m.levels.map((x) => x.qps ?? 0)), 1)} <small>consultas/s</small></dd></div>
            </dl>

            <div className="section-title"><h3>Latencia por nivel de la rampa</h3><span>{m.queries_per_user} consultas por usuario</span></div>
            <LatencyChart levels={m.levels} slo={slo} target={target} />

            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Usuarios</th><th className="r">Consultas</th><th className="r">Fallidas</th><th className="r">p50</th><th className="r">p90</th><th className="r">p95</th><th className="r">Máx.</th><th className="r">Consultas/s</th><th className="r">Duración</th></tr></thead>
                <tbody>
                  {m.levels.map((x) => (
                    <tr key={x.run_id}>
                      <td className="num"><b>{x.level}</b></td><td className="r">{num(x.queries)}</td>
                      <td className="r" style={{ color: x.failed_queries ? 'var(--fail)' : undefined }}>{num(x.failed_queries)}</td>
                      <td className="r">{secs(x.p50)}</td><td className="r">{secs(x.p90)}</td>
                      <td className="r" style={{ color: (x.p95 ?? 0) > slo ? 'var(--fail)' : undefined, fontWeight: 650 }}>{secs(x.p95)}</td>
                      <td className="r">{secs(x.max)}</td><td className="r">{num(x.qps, 1)}</td><td className="r">{num(x.duration_s, 0)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {m.levels.some((x) => x.error_samples?.length) && (
              <div className="notice notice--fail" style={{ marginTop: 'var(--sp-4)' }}>
                <TriangleAlert aria-hidden />
                <div><strong>Errores registrados</strong>{[...new Set(m.levels.flatMap((x) => x.error_samples))].slice(0, 3).map((e) => <p key={e} className="mono" style={{ wordBreak: 'break-word' }}>{e}</p>)}</div>
              </div>
            )}

            <div className="section-title"><h3>Visuales más lentas en el último nivel</h3><span>Crecimiento del p95 frente al primer nivel</span></div>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Visual</th><th className="r">p95 primer nivel</th><th className="r">p95</th><th className="r">Crecimiento</th><th>Diagnóstico</th></tr></thead>
                <tbody>
                  {m.slow_visuals.map((v) => (
                    <tr key={v.visual}>
                      <td><b>{v.visual}</b></td><td className="r">{secs(v.p95_first_level)}</td>
                      <td className="r" style={{ color: v.slow ? 'var(--fail)' : undefined, fontWeight: 650 }}>{secs(v.p95)}</td>
                      <td className="r">{v.growth ? `×${num(v.growth, 1)}` : '–'}</td>
                      <td>{!v.slow ? <span className="muted">Dentro del umbral</span> : (v.growth ?? 0) >= 3 ? 'Contención con la concurrencia' : 'Consulta lenta incluso sin carga'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {m.slow_queries.length > 0 && (
              <>
                <div className="section-title"><h3>Consultas DAX más lentas</h3><span>Ábrelas en DAX Studio con Server Timings</span></div>
                {m.slow_queries.map((q) => (
                  <details className="dax" key={`${q.visual}-${q.query_number}`}>
                    <summary><b>{q.visual}</b><span className="num">p95 {secs(q.p95)}, {num(q.rows)} filas</span></summary>
                    <pre>{q.dax}</pre>
                  </details>
                ))}
              </>
            )}
          </div>
        );
      })}
      <p className="field__hint" style={{ marginTop: 'var(--sp-5)' }}>La latencia es la del cliente y los usuarios repiten consultas: la caché del motor hace que el resultado sea optimista.</p>
    </>
  );
}

// ---------------- Buenas prácticas ----------------
function ModelPanel({ review, sku }: { review: ModelReview | null; sku: string }) {
  const groups = useMemo(() => {
    const m = new Map<string, { rule: string; severity: string; category: string; url: string; objects: string[] }>();
    for (const f of review?.findings ?? []) {
      const g = m.get(f.rule) ?? { rule: f.rule, severity: f.severity, category: f.category, url: f.url, objects: [] };
      g.objects.push(f.object_name);
      m.set(f.rule, g);
    }
    const order = { Error: 0, Warning: 1, Info: 2 } as Record<string, number>;
    return [...m.values()].sort((a, b) => order[a.severity] - order[b.severity] || b.objects.length - a.objects.length);
  }, [review]);
  if (!review) return <p>No hay revisión del modelo.</p>;
  if (review.error) return <div className="notice notice--fail"><TriangleAlert aria-hidden /><div><strong>La revisión falló</strong><p>{review.error}</p></div></div>;
  const vp = review.vertipaq;
  const count = (s: string) => (review.findings ?? []).filter((f) => f.severity === s).length;
  const limits: Record<string, number> = { F2: 3, F4: 3, F8: 3, F16: 5, F32: 10, F64: 25, F128: 50, F256: 100, F512: 200, F1024: 400, F2048: 400 };
  const limitMb = (limits[sku] ?? 25) * 1024;
  const memPct = vp?.model_size_mb ? (100 * vp.model_size_mb) / limitMb : null;
  return (
    <>
      <dl className="kv">
        <div><dt>Reglas Error</dt><dd data-s={count('Error') ? 'FAIL' : 'PASS'}>{count('Error')}</dd></div>
        <div><dt>Reglas Warning</dt><dd data-s={count('Warning') > 30 ? 'WARN' : undefined}>{count('Warning')}</dd></div>
        <div><dt>Tamaño en memoria</dt><dd>{num(vp?.model_size_mb)} <small>MB</small></dd></div>
        <div><dt>Del máximo de {sku}</dt><dd data-s={(memPct ?? 0) > 50 ? 'WARN' : undefined}>{pct(memPct)}</dd></div>
      </dl>

      <div className="section-title"><h3>Best Practice Analyzer</h3><span>{groups.length} reglas, {review.findings?.length ?? 0} objetos</span></div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Regla</th><th>Severidad</th><th>Categoría</th><th>Objetos</th></tr></thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.rule}>
                <td><b>{g.rule}</b>{g.url && <> <a href={g.url} target="_blank" rel="noreferrer" aria-label={`Documentación de ${g.rule}`}><ExternalLink size={12} aria-hidden /></a></>}</td>
                <td><StatusTag status={g.severity === 'Error' ? 'FAIL' : g.severity === 'Warning' ? 'WARN' : 'SKIP'} label={g.severity} /></td>
                <td className="muted">{g.category}</td>
                <td className="mono" style={{ fontSize: 12 }}>{g.objects.slice(0, 4).join(', ')}{g.objects.length > 4 ? ` y ${g.objects.length - 4} más` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {vp && vp.top_columns.length > 0 && (
        <>
          <div className="section-title"><h3>Columnas que más pesan (VertiPaq)</h3><span>Una columna por encima del 20 % del modelo es candidata a optimizar</span></div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Columna</th><th>Tipo</th><th className="r">Cardinalidad</th><th className="r">MB</th><th style={{ width: '28%' }}>% del modelo</th></tr></thead>
              <tbody>
                {vp.top_columns.map((c) => (
                  <tr key={`${c.table}.${c.column}`}>
                    <td className="mono" style={{ fontSize: 12 }}>{c.table}[{c.column}]</td><td className="muted">{c.data_type ?? '–'}</td>
                    <td className="r">{num(c.cardinality)}</td><td className="r">{num(c.size_mb, 1)}</td>
                    <td><div className="row" style={{ flexWrap: 'nowrap' }}><div className="meter" data-s={(c.pct_of_model ?? 0) > 20 ? 'WARN' : 'PASS'} style={{ flex: 1 }}><span style={{ width: `${Math.min(100, c.pct_of_model ?? 0)}%` }} /><i className="limit" style={{ left: '20%' }} /></div><span className="num" style={{ width: 52, textAlign: 'right' }}>{pct(c.pct_of_model, 1)}</span></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

// ---------------- Capacity Metrics ----------------
function Gauge({ label, value, limit, warn, unit = '%' }: { label: string; value?: number; limit: number; warn?: number; unit?: string }) {
  const v = value ?? 0;
  const s: Status = v >= limit ? 'FAIL' : warn != null && v >= warn ? 'WARN' : 'PASS';
  const scale = Math.max(limit * 1.25, v * 1.05, 100);
  return (
    <div className="field">
      <div className="row" style={{ justifyContent: 'space-between' }}><span className="label">{label}</span><span className="num" style={{ fontWeight: 650, color: s === 'FAIL' ? 'var(--fail)' : s === 'WARN' ? 'var(--warn)' : undefined }}>{num(v, 1)} {unit}</span></div>
      <div className="meter" data-s={s} role="meter" aria-valuenow={v} aria-valuemin={0} aria-valuemax={scale} aria-label={label}>
        <span style={{ width: `${(100 * v) / scale}%` }} /><i className="limit" style={{ left: `${(100 * limit) / scale}%` }} title={`Límite ${limit} ${unit}`} />
      </div>
      <span className="field__hint">Límite {num(limit)} {unit}</span>
    </div>
  );
}

function CapacityPanel({ cap, cfg }: { cap: Capacity | null; cfg: { max_utilization_pct: number; warn_interactive_delay_pct: number; max_interactive_delay_pct: number; warn_interactive_rejection_pct: number; max_tooling_cu_share_pct: number } }) {
  if (!cap) return <p>No hay datos de Capacity Metrics.</p>;
  if (cap.error) return <div className="notice notice--fail"><TriangleAlert aria-hidden /><div><strong>No se pudo leer Capacity Metrics</strong><p>{cap.error}</p></div></div>;
  return (
    <>
      <div className="grid-2">
        <Gauge label="Utilización pico de la capacidad" value={cap.peak_utilization_pct} limit={cfg.max_utilization_pct} />
        <Gauge label="Retraso interactivo (% del umbral)" value={cap.peak_interactive_delay_pct} limit={cfg.max_interactive_delay_pct} warn={cfg.warn_interactive_delay_pct} />
        <Gauge label="Rechazo interactivo (% del umbral)" value={cap.peak_interactive_rejection_pct} limit={100} warn={cfg.warn_interactive_rejection_pct} />
        <Gauge label="CU del generador de carga (% del día)" value={cap.tooling?.share_pct} limit={cfg.max_tooling_cu_share_pct} />
      </div>
      <p className="field__hint" style={{ marginTop: 'var(--sp-3)' }}>
        Versión de la app {cap.version ?? '–'}, {cap.timepoints_in_window ?? 0} timepoints de 30 s en la ventana del test, utilización media {pct(cap.avg_utilization_pct, 1)}, carry-over pico {pct(cap.peak_carryover_pct, 1)}.
      </p>

      {cap.model?.operations?.length ? (
        <>
          <div className="section-title"><h3>Operaciones del modelo</h3><span>Día completo: incluye otra actividad sobre el modelo</span></div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Operación</th><th className="r">CU (s)</th><th className="r">Operaciones</th><th className="r">CU por operación</th><th className="r">Fallidas</th><th className="r">Rechazadas</th><th className="r">Throttling</th></tr></thead>
              <tbody>
                {cap.model.operations.map((o) => (
                  <tr key={o.operation}>
                    <td><b>{o.operation}</b></td><td className="r">{num(o.cu_s, 1)}</td><td className="r">{num(o.operations)}</td>
                    <td className="r">{num(o.cu_s_per_operation, 3)}</td>
                    <td className="r" style={{ color: o.failed ? 'var(--fail)' : undefined }}>{num(o.failed)}</td>
                    <td className="r" style={{ color: o.rejected ? 'var(--fail)' : undefined }}>{num(o.rejected)}</td>
                    <td className="r">{num(o.throttling_min, 1)} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : <p className="field__hint" style={{ marginTop: 'var(--sp-4)' }}>El modelo no aparece en la tabla diaria de Capacity Metrics.</p>}
    </>
  );
}

// ---------------- Firma y promoción ----------------
function SignOff({ run, ev }: { run: RunRecord; ev: Evidence | undefined }) {
  const { service, account, patchRun } = useGate();
  const verdict = ev?.verdict ?? null;
  const blockers = promotionBlockers(verdict, run.dataset_id, run.promoted_at ? dateTime(run.promoted_at) : undefined);
  const promotable = verdict?.promotable ?? false;
  const [path, setPath] = useState<{ status: 'idle' | 'loading' | 'done' | 'error'; value: PromotionPath | null; error?: string }>({ status: 'idle', value: null });
  const [state, setState] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null });
  const [typed, setTyped] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);

  const findPath = async () => {
    setPath({ status: 'loading', value: null });
    try {
      setPath({ status: 'done', value: await service.promotionPath(run.workspace_id) });
    } catch (e) {
      setPath({ status: 'error', value: null, error: (e as Error).message });
    }
  };

  useEffect(() => {
    if (promotable && !run.promoted_at && service.demo) void findPath();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promotable, run.promoted_at]);

  const promote = async () => {
    if (!path.value || !account) return;
    setState({ busy: true, error: null });
    try {
      const items = [{ sourceItemId: run.dataset_id, itemType: 'SemanticModel' }];
      if (run.report_id) items.push({ sourceItemId: run.report_id, itemType: 'Report' });
      const r = await service.promote(path.value, items, `Gate ${verdict?.verdict} ${run.run_id} firmado por ${account.username}`);
      if (r.status !== 'Succeeded') throw new Error(`El despliegue terminó en estado ${r.status}. Revisa el deployment pipeline en Fabric.`);
      await patchRun(run.run_id, { promoted_at: new Date().toISOString(), promoted_by: account.username, promoted_to: path.value.target.workspaceName ?? path.value.target.displayName });
      dialog.current?.close();
      setState({ busy: false, error: null });
    } catch (e) {
      setState({ busy: false, error: (e as Error).message });
    }
  };

  if (run.promoted_at) {
    return (
      <section className="sheet signoff" aria-label="Promoción">
        <h3><ShieldCheck size={18} aria-hidden />Puesto en servicio</h3>
        <SignatureBox run={run} name={run.promoted_by} when={dateTime(run.promoted_at)} />
        <p className="field__hint" style={{ marginTop: 'var(--sp-3)' }}>Desplegado en <b>{run.promoted_to}</b>.</p>
        <span className="stamp">Promocionado</span>
      </section>
    );
  }

  return (
    <section className="sheet signoff" aria-label="Promoción">
      <h3><PenLine size={18} aria-hidden />Autorización de puesta en servicio</h3>
      {blockers.length > 0 ? (
        <div className="notice" style={{ marginTop: 'var(--sp-4)' }}>
          <OctagonX aria-hidden />
          <div><strong>No se puede promocionar</strong>{blockers.map((b) => <p key={b}>{b}</p>)}<p>Aplica las mejoras de prioridad alta y lanza un gate nuevo.</p></div>
        </div>
      ) : (
        <>
          {path.status === 'idle' && (
            <div className="stack" style={{ marginTop: 'var(--sp-4)' }}>
              <p className="field__hint">El veredicto permite promocionar. Busca la ruta del deployment pipeline del workspace.</p>
              <button className="btn" onClick={findPath}><ArrowRight size={16} aria-hidden />Buscar la ruta de promoción</button>
            </div>
          )}
          {path.status === 'loading' && <div className="stack" style={{ marginTop: 'var(--sp-4)' }} aria-busy="true"><div className="skeleton" /><div className="skeleton" style={{ width: '60%' }} /></div>}
          {path.status === 'error' && (
            <div className="stack" style={{ marginTop: 'var(--sp-4)' }}>
              <p className="field__error">No se pudo leer los deployment pipelines: {path.error}</p>
              <button className="btn" onClick={findPath}>Reintentar</button>
            </div>
          )}
          {path.status === 'done' && !path.value && (
            <div className="notice" style={{ marginTop: 'var(--sp-4)' }}>
              <TriangleAlert aria-hidden />
              <div><strong>Sin ruta de promoción</strong><p>Ningún deployment pipeline al que tengas acceso tiene «{run.workspace_name}» en un stage con otro stage detrás. Asigna el workspace en Fabric o promociona con tu proceso habitual citando el certificado {run.run_id}.</p></div>
            </div>
          )}
          {path.value && (
            <>
              <div className="signoff__route" aria-label="Ruta de promoción">
                <div><small>{path.value.source.displayName}</small><b>{path.value.source.workspaceName ?? run.workspace_name}</b></div>
                <ArrowRight size={18} aria-hidden />
                <div><small>{path.value.target.displayName}</small><b>{path.value.target.workspaceName ?? path.value.target.displayName}</b></div>
              </div>
              <p className="field__hint">Se desplegarán el modelo {run.dataset_name}{run.report_name ? ` y el informe ${run.report_name}` : ''} con el deployment pipeline «{path.value.pipelineName}».</p>
              <button className="btn btn--primary" style={{ marginTop: 'var(--sp-4)', width: '100%' }} onClick={() => { setTyped(''); dialog.current?.showModal(); }}>
                <PenLine size={16} aria-hidden />Firmar y promocionar
              </button>
            </>
          )}
        </>
      )}

      <dialog ref={dialog} className="confirm" aria-labelledby="confirm-t">
        <form method="dialog" onSubmit={(e) => { e.preventDefault(); void promote(); }}>
          <h2 id="confirm-t">Firmar la puesta en servicio</h2>
          <p>Vas a desplegar <b>{run.dataset_name}</b>{run.report_name ? <> y <b>{run.report_name}</b></> : null} de <b>{path.value?.source.displayName}</b> a <b>{path.value?.target.displayName}</b> con el certificado <b className="num">{run.run_id}</b> ({verdict?.verdict}). Esta acción sobrescribe el contenido del destino.</p>
          <label className="field">
            <span className="label">Escribe el nombre del modelo para confirmar</span>
            <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus />
          </label>
          {state.error && <p className="field__error">{state.error}</p>}
          <div className="actions">
            <button type="button" className="btn" onClick={() => dialog.current?.close()} disabled={state.busy}>Volver</button>
            <button type="submit" className="btn btn--primary" disabled={typed.trim() !== run.dataset_name || state.busy}>
              <FileText size={16} aria-hidden />{state.busy ? 'Desplegando…' : 'Firmar y desplegar'}
            </button>
          </div>
        </form>
      </dialog>
    </section>
  );
}
