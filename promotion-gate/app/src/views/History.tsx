import { ArrowDown, ArrowUp, Plus } from 'lucide-react';
import { useMemo, useState } from 'react';
import { StatusTag } from '../components/StatusTag';
import { dateTime, duration } from '../lib/format';
import { ACTIVE, useGate } from '../lib/store';
import type { RunRecord } from '../lib/types';

type Key = 'started_at' | 'dataset_name' | 'workspace_name' | 'verdict';
type Filter = 'all' | 'active' | 'PASS' | 'WARN' | 'FAIL';

function stateOf(r: RunRecord) {
  if (ACTIVE.includes(r.status)) return <StatusTag status="RUN" />;
  if (r.verdict) return <StatusTag status={r.verdict} />;
  return <StatusTag status="SKIP" label={r.status === 'Cancelled' ? 'Cancelado' : 'Sin veredicto'} />;
}

export function History() {
  const { runs, go, runsShared } = useGate();
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: 'started_at', dir: -1 });
  const [filter, setFilter] = useState<Filter>('all');

  const rows = useMemo(() => runs
    .filter((r) => filter === 'all' || (filter === 'active' ? ACTIVE.includes(r.status) : r.verdict === filter))
    .sort((a, b) => sort.dir * String(a[sort.key] ?? '').localeCompare(String(b[sort.key] ?? ''), 'es')), [runs, sort, filter]);

  const th = (key: Key, label: string) => (
    <th aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button onClick={() => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : 1 }))}>
        {label}{sort.key === key && (sort.dir === 1 ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />)}
      </button>
    </th>
  );

  const counts = {
    all: runs.length, active: runs.filter((r) => ACTIVE.includes(r.status)).length,
    PASS: runs.filter((r) => r.verdict === 'PASS').length, WARN: runs.filter((r) => r.verdict === 'WARN').length,
    FAIL: runs.filter((r) => r.verdict === 'FAIL').length,
  };

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Runs del gate</h1>
          <p>{runsShared ? 'Historial del equipo, guardado en la base de datos de la app.' : 'Historial de este navegador. Despliega la app con Rayfin para compartirlo con el equipo.'} La auditoría oficial está en la tabla Delta gate_runs.</p>
        </div>
        <button className="btn btn--primary" onClick={() => go({ name: 'new' })}><Plus size={16} aria-hidden />Nuevo gate</button>
      </header>

      {runs.length === 0 ? (
        <div className="sheet empty">
          <h2>Todavía no hay runs</h2>
          <p>Cuando lances el primer gate aparecerá aquí con su certificado, su estado en vivo y, al terminar, su veredicto.</p>
          <button className="btn btn--primary" onClick={() => go({ name: 'new' })}><Plus size={16} aria-hidden />Lanzar el primer gate</button>
        </div>
      ) : (
        <div className="sheet" style={{ padding: 'var(--sp-5)' }}>
          <div className="filters" role="group" aria-label="Filtrar runs">
            {([['all', 'Todos'], ['active', 'En curso'], ['PASS', 'Aptos'], ['WARN', 'Con observaciones'], ['FAIL', 'No aptos']] as [Filter, string][]).map(([f, label]) => (
              <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>{label} ({counts[f]})</button>
            ))}
          </div>
          {rows.length === 0 ? <p className="field__hint">Ningún run con este filtro.</p> : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Certificado</th>{th('dataset_name', 'Modelo')}{th('workspace_name', 'Workspace')}<th>Lanzado por</th>
                    {th('started_at', 'Inicio')}<th className="r">Duración</th>{th('verdict', 'Estado')}<th>Promoción</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.run_id} data-click tabIndex={0} onClick={() => go({ name: 'run', runId: r.run_id })}
                      onKeyDown={(e) => { if (e.key === 'Enter') go({ name: 'run', runId: r.run_id }); }}>
                      <td className="num" style={{ fontWeight: 650, whiteSpace: 'nowrap' }}>{r.run_id}</td>
                      <td><b>{r.dataset_name}</b>{r.report_name && <div className="muted">{r.report_name}</div>}</td>
                      <td>{r.workspace_name}</td>
                      <td className="muted">{r.requested_by}</td>
                      <td className="num" style={{ whiteSpace: 'nowrap' }}>{dateTime(r.started_at)}</td>
                      <td className="r">{duration(r.started_at, r.finished_at)}</td>
                      <td>{stateOf(r)}</td>
                      <td className="muted">{r.promoted_at ? `A ${r.promoted_to}, ${dateTime(r.promoted_at)}` : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </>
  );
}
