import { Check, X } from 'lucide-react';
import { msDuration } from '../lib/format';
import type { PhaseStatus } from '../lib/gate';
import type { LevelProgress } from '../lib/service';

const STATE_TEXT = { pending: 'Pendiente', running: 'En curso', done: 'Hecho', failed: 'Error', skipped: 'Omitida' } as const;

/** Ruta del run: solo la fase activa a tinta plena (lo demás en tinta suave). */
export function PhaseRoute({ phases, levels }: { phases: PhaseStatus[]; levels: LevelProgress[] }) {
  return (
    <ol className="route" aria-label="Fases del gate">
      {phases.map((p) => (
        <li key={p.id} className="route__stop" data-state={p.state} aria-current={p.state === 'running' ? 'step' : undefined}>
          <span className="route__dot" aria-hidden>
            {p.state === 'done' && <Check strokeWidth={3} />}
            {p.state === 'failed' && <X strokeWidth={3} />}
          </span>
          <span className="route__name">{p.label}</span>
          <span className="route__meta">
            {STATE_TEXT[p.state]}
            {p.state === 'done' && p.durationMs ? `, ${msDuration(p.durationMs)}` : ''}
            {p.state === 'pending' || p.state === 'running' ? <><br />{p.detail}</> : null}
          </span>
          {p.id === 'load' && levels.length > 0 && (
            <span className="route__levels" aria-label="Niveles de la rampa">
              {levels.map((l) => (
                <span key={l.level} data-done={l.done} title={l.done ? `${l.level} usuarios: terminado` : `${l.level} usuarios: en curso`}>
                  {l.level}
                </span>
              ))}
            </span>
          )}
          {p.message && <span className="route__meta" style={{ color: 'var(--fail)' }}>{p.message.slice(0, 140)}</span>}
        </li>
      ))}
    </ol>
  );
}
