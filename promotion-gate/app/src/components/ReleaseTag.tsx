import { AREA_LABEL, dateTime } from '../lib/format';
import type { Area, Status, Verdict } from '../lib/types';
import { StatusTag } from './StatusTag';

const WORD = { PASS: 'Apto para producción', WARN: 'Apto con observaciones', FAIL: 'No apto', RUN: 'En inspección' } as const;
const HEAD = { PASS: 'Certificado de aptitud', WARN: 'Certificado condicionado', FAIL: 'Etiqueta de rechazo', RUN: 'Inspección en curso' } as const;

interface Props {
  runId: string;
  dataset: string;
  workspace: string;
  verdict: Verdict | null;
  runningPhase?: string;
}

/** La etiqueta de estado que cuelga del modelo: verde apto, amarilla con observaciones, roja no apto. */
export function ReleaseTag({ runId, dataset, workspace, verdict, runningPhase }: Props) {
  const v = verdict?.verdict ?? 'RUN';
  return (
    <section className="release" data-v={v} aria-label={`Veredicto: ${WORD[v]}`}>
      <svg className="release__string" viewBox="0 0 120 46" aria-hidden>
        <path d="M60 0 C 52 14, 46 26, 60 40" fill="none" stroke="#8a93a5" strokeWidth="1.6" />
        <path d="M60 0 C 70 16, 74 28, 60 40" fill="none" stroke="#a7aebd" strokeWidth="1.2" />
      </svg>
      <div className="release__card" key={v}>
        <div className="release__head">{HEAD[v]}</div>
        <div className="release__word">{WORD[v]}</div>
        {v === 'RUN' && runningPhase && <div style={{ marginTop: 6, fontSize: 'var(--fs-sm)' }}>Fase actual: <b>{runningPhase}</b></div>}
        <dl className="release__fields">
          <div style={{ gridColumn: '1 / -1' }}><dt data-n="1">Certificado</dt><dd className="num" title={runId}>{runId}</dd></div>
          <div><dt data-n="2">Modelo</dt><dd title={dataset}>{dataset}</dd></div>
          <div><dt data-n="3">Workspace</dt><dd title={workspace}>{workspace}</dd></div>
          <div><dt data-n="4">Emitido</dt><dd>{verdict ? dateTime(verdict.evaluated_utc) : '–'}</dd></div>
        </dl>
        {verdict && (
          <div className="release__areas">
            {(Object.entries(verdict.areas) as [Area, Status][]).map(([a, s]) => (
              <div key={a}><span>{AREA_LABEL[a]}</span><StatusTag status={s} /></div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
