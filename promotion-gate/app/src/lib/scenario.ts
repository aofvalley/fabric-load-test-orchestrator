/**
 * Escenarios de navegación para el test de carga, en el formato de exportación de Performance Analyzer que lee
 * RunPerfScenario_v3 (eventos «User Action», «Visual Container Lifecycle» y «Execute DAX Query»).
 */

export interface ScenarioSummary { queries: number; actions: number; visuals: number; durationSec: number }

interface PaEvent { name?: string; start?: string; end?: string; metrics?: Record<string, unknown> }

export function inspectScenario(text: string): ScenarioSummary {
  let doc: { events?: PaEvent[] };
  try {
    doc = JSON.parse(text.replace(/^\uFEFF/, ''));
  } catch {
    throw new Error('El fichero no es JSON. Exporta el escenario desde Performance Analyzer con «Export».');
  }
  const events = Array.isArray(doc?.events) ? doc.events : null;
  if (!events) throw new Error('El JSON no tiene la lista «events» de Performance Analyzer.');
  const queries = events.filter((e) => e.name === 'Execute DAX Query' && typeof e.metrics?.QueryText === 'string');
  if (!queries.length) throw new Error('El escenario no contiene consultas DAX: graba interactuando con el informe.');
  const visuals = new Set(events.filter((e) => e.name === 'Visual Container Lifecycle').map((e) => String(e.metrics?.visualId ?? '')));
  const times = events.flatMap((e) => [e.start, e.end]).filter(Boolean).map((t) => Date.parse(String(t))).filter((t) => !Number.isNaN(t));
  return {
    queries: queries.length,
    actions: events.filter((e) => e.name === 'User Action').length,
    visuals: visuals.size,
    durationSec: times.length ? Math.round((Math.max(...times) - Math.min(...times)) / 1000) : 0,
  };
}

export interface MeasureInfo { table: string; name: string; expression?: string }
export interface ColumnInfo { table: string; name: string; dataType: string; hidden?: boolean }

const quoteTable = (t: string) => `'${t.replace(/'/g, "''")}'`;
const quoteName = (n: string) => `[${n.replace(/]/g, ']]')}]`;

/** Lee medidas y columnas visibles con INFO.VIEW (no requiere permisos de administrador del modelo). */
export const SCHEMA_DAX = {
  measures: `EVALUATE SELECTCOLUMNS(FILTER(INFO.VIEW.MEASURES(), NOT [IsHidden]), "table", [Table], "name", [Name])`,
  columns: `EVALUATE SELECTCOLUMNS(FILTER(INFO.VIEW.COLUMNS(), [Type] <> "RowNumber"), "table", [Table], "name", [Name], "dataType", [DataType], "hidden", [IsHidden])`,
};

function pick<T>(rows: Record<string, unknown>[], key: string): T[] {
  return rows.map((r) => {
    const k = Object.keys(r).find((x) => x.toLowerCase().endsWith(`[${key}]`) || x.toLowerCase() === key);
    return (k ? r[k] : undefined) as T;
  });
}

export function parseSchemaRows(measureRows: Record<string, unknown>[], columnRows: Record<string, unknown>[]) {
  const mt = pick<string>(measureRows, 'table'), mn = pick<string>(measureRows, 'name');
  const ct = pick<string>(columnRows, 'table'), cn = pick<string>(columnRows, 'name'), cd = pick<string>(columnRows, 'datatype');
  const ch = pick<unknown>(columnRows, 'hidden');
  return {
    measures: mt.map((t, i) => ({ table: t, name: mn[i] })).filter((m) => m.table && m.name) as MeasureInfo[],
    columns: ct.map((t, i) => ({ table: t, name: cn[i], dataType: String(cd[i] ?? ''), hidden: ch[i] === true || ch[i] === 'True' }))
      .filter((c) => c.table && c.name) as ColumnInfo[],
  };
}

/**
 * Escenario SINTÉTICO: tarjetas (ROW de cada medida) y desgloses (TOPN de SUMMARIZECOLUMNS por columnas de texto
 * o fecha), agrupados en «páginas» con pausas de usuario. Sirve para un primer run; no sustituye a una grabación real.
 */
const NUMERIC = /^(integer|int64|number|double|decimal|currency)$/i;
const isKey = (c: ColumnInfo) => /(^|\s)(id|key|sk|código|codigo)$/i.test(c.name.trim());

/** Modelos sin medidas: agregaciones implícitas (SUM) de las columnas numéricas que no son claves. */
const DATE_PART = /^(año|ano|year|mes|month|día|dia|day|trimestre|quarter|semana|week)(\s|$)/i;

export function implicitMeasures(columns: ColumnInfo[]): MeasureInfo[] {
  return columns.filter((c) => NUMERIC.test(c.dataType) && !isKey(c) && !DATE_PART.test(c.name.trim())).map((c) => ({
    table: c.table, name: `Suma de ${c.name}`, expression: `SUM(${quoteTable(c.table)}${quoteName(c.name)})`,
  }));
}

export function syntheticScenario(measures: MeasureInfo[], columns: ColumnInfo[],
  opts: { maxMeasures?: number; pages?: number; thinkSec?: number; start?: Date } = {}): string {
  const maxMeasures = opts.maxMeasures ?? 8;
  const pages = opts.pages ?? 3;
  const thinkSec = opts.thinkSec ?? 8;
  const visibleMeasures = measures.filter((m) => m.name);
  const ms = (visibleMeasures.length ? visibleMeasures : implicitMeasures(columns)).slice(0, maxMeasures);
  if (!ms.length) throw new Error('El modelo no tiene medidas visibles ni columnas numéricas con las que construir un escenario.');
  const measureTables = new Set(ms.map((m) => m.table));
  const attrs = columns.filter((c) => !c.hidden && /string|text|date/i.test(c.dataType));
  const dims = attrs.filter((c) => !measureTables.has(c.table)).slice(0, 6);
  const groupBy = dims.length ? dims : attrs.slice(0, 6);
  const value = (m: MeasureInfo) => m.expression ?? quoteName(m.name);

  const events: PaEvent[] = [];
  let t = (opts.start ?? new Date('2026-01-01T09:00:00Z')).getTime();
  const iso = (ms_: number) => new Date(ms_).toISOString();
  let visualN = 0;
  const perPage = Math.ceil(ms.length / pages);
  for (let p = 0; p < pages; p++) {
    const pageMeasures = ms.slice(p * perPage, (p + 1) * perPage);
    if (!pageMeasures.length) break;
    events.push({ name: 'User Action', start: iso(t), end: iso(t + 50), metrics: { sourceLabel: `Página ${p + 1}` } });
    t += 100;
    const queries: { title: string; dax: string }[] = [];
    pageMeasures.forEach((m, idx) => {
      queries.push({ title: `Tarjeta ${m.name}`, dax: `EVALUATE ROW("v", ${value(m)})` });
      const col = groupBy.length ? groupBy[(p * perPage + idx) % groupBy.length] : null;
      if (col) {
        queries.push({
          title: `${m.name} por ${col.name}`,
          dax: `EVALUATE TOPN(100, SUMMARIZECOLUMNS(${quoteTable(col.table)}${quoteName(col.name)}, "v", ${value(m)}), [v], DESC)`,
        });
      }
    });
    for (const q of queries) {
      visualN += 1;
      events.push({ name: 'Visual Container Lifecycle', start: iso(t), end: iso(t + 400),
        metrics: { visualTitle: q.title, visualId: `synthetic-${visualN}` } });
      events.push({ name: 'Execute DAX Query', start: iso(t + 10), end: iso(t + 300), metrics: { QueryText: q.dax } });
      t += 20;
    }
    t += thinkSec * 1000;
  }
  return JSON.stringify({ version: '1.1.0', synthetic: true, events }, null, 1);
}
