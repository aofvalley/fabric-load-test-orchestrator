const nf = (d: number) => new Intl.NumberFormat('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d });

export function num(v: number | null | undefined, digits = 0): string {
  return v == null || Number.isNaN(v) ? '–' : nf(digits).format(v);
}

export function secs(v: number | null | undefined): string {
  if (v == null) return '–';
  return v < 10 ? `${nf(2).format(v)} s` : `${nf(1).format(v)} s`;
}

export function pct(v: number | null | undefined, digits = 0): string {
  return v == null ? '–' : `${nf(digits).format(v)} %`;
}

export function dateTime(iso: string | undefined | null): string {
  if (!iso) return '–';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(d);
}

export function duration(fromIso?: string, toIso?: string): string {
  if (!fromIso) return '–';
  const ms = (toIso ? Date.parse(toIso) : Date.now()) - Date.parse(fromIso);
  if (!(ms >= 0)) return '–';
  const m = Math.round(ms / 60000);
  if (m < 1) return '< 1 min';
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function msDuration(ms?: number): string {
  if (!ms) return '';
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export const AREA_LABEL = { model_review: 'Buenas prácticas', load_test: 'Test de carga', capacity: 'Capacity Metrics' } as const;
