import { num } from '../lib/format';
import type { Level } from '../lib/types';

interface Props { levels: Level[]; slo: number; target: number }

/** p50 y p95 por nivel de la rampa frente al SLO del equipo. El eje X son niveles, no tiempo. */
function niceStep(v: number): number {
  const p = 10 ** Math.floor(Math.log10(v || 1));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

export function LatencyChart({ levels, slo, target }: Props) {
  const data = levels.filter((l) => l.p95 != null);
  if (!data.length) return <p className="muted">Ningún nivel tiene consultas correctas que medir.</p>;
  const W = 640, H = 240, L = 52, R = 16, T = 16, B = 44, PAD = 48;
  const raw = Math.max(slo * 1.25, ...data.map((d) => d.p95 ?? 0));
  const step = niceStep(raw / 4);
  const yMax = Math.ceil((raw * 1.05) / step) * step;
  const x = (i: number) => (data.length === 1 ? L + (W - L - R) / 2 : L + PAD + (i * (W - L - R - 2 * PAD)) / (data.length - 1));
  const y = (v: number) => T + (H - T - B) * (1 - v / yMax);
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, i) => i * step);
  const line = (k: 'p50' | 'p95') => data.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d[k] ?? 0).toFixed(1)}`).join(' ');

  return (
    <figure style={{ margin: 0 }}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Latencia por nivel: ${data.map((d) => `${d.level} usuarios p95 ${num(d.p95, 2)} s`).join(', ')}. SLO p95 ${slo} s.`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
            <text x={L - 8} y={y(t) + 4} textAnchor="end">{num(t, step < 1 ? 1 : 0)} s</text>
          </g>
        ))}
        <line className="axis" x1={L} x2={W - R} y1={H - B} y2={H - B} />
        <line className="slo" x1={L} x2={W - R} y1={y(slo)} y2={y(slo)} />
        <text x={W - R} y={y(slo) - 6} textAnchor="end" style={{ fill: 'var(--fail)', fontWeight: 600 }}>SLO p95 {num(slo, 1)} s</text>
        <path className="p50" d={line('p50')} />
        <path className="p95" d={line('p95')} />
        {data.map((d, i) => (
          <g key={d.level}>
            <circle className="pt50" cx={x(i)} cy={y(d.p50 ?? 0)} r={3.5} />
            <circle className={`pt95${(d.p95 ?? 0) > slo ? ' over' : ''}`} cx={x(i)} cy={y(d.p95 ?? 0)} r={5} />
            <text x={x(i)} y={H - B + 18} textAnchor="middle" style={{ fill: 'var(--ink)', fontWeight: d.level === target ? 700 : 500 }}>
              {d.level} usuarios
            </text>
            <text x={x(i)} y={H - B + 33} textAnchor="middle" style={{ fill: d.failed_queries ? 'var(--fail)' : 'var(--ink-3)' }}>
              {d.failed_queries ? `${d.failed_queries} fallidas` : 'sin errores'}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="legend">
        <span><i />p95</span>
        <span><i className="p50" />p50</span>
        <span><i className="slo" />SLO del equipo</span>
        <span>Objetivo: <b>{target} usuarios</b></span>
      </figcaption>
    </figure>
  );
}
