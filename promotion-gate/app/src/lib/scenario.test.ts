import { describe, expect, it } from 'vitest';
import { inspectScenario, parseSchemaRows, syntheticScenario } from './scenario';

const measures = [{ table: 'Hechos', name: 'Ventas' }, { table: 'Hechos', name: "Margen [%]" }, { table: 'Hechos', name: 'Unidades' }];
const columns = [
  { table: 'Fecha', name: 'Mes', dataType: 'Text' },
  { table: "Tienda's", name: 'Región', dataType: 'Text' },
  { table: 'Hechos', name: 'Importe', dataType: 'Decimal' },
];

describe('escenario de Performance Analyzer', () => {
  it('describe un escenario válido', () => {
    const s = inspectScenario(syntheticScenario(measures, columns, { pages: 2, thinkSec: 5 }));
    expect(s.actions).toBe(2);
    expect(s.queries).toBe(6);
    expect(s.visuals).toBe(6);
    expect(s.durationSec).toBeGreaterThanOrEqual(5);
  });

  it('rechaza ficheros que no son una exportación de Performance Analyzer', () => {
    expect(() => inspectScenario('no json')).toThrow(/no es JSON/);
    expect(() => inspectScenario('{"foo":1}')).toThrow(/events/);
    expect(() => inspectScenario('{"events":[{"name":"User Action"}]}')).toThrow(/consultas DAX/);
  });

  it('escapa nombres de tablas y medidas en el DAX sintético', () => {
    const json = JSON.parse(syntheticScenario(measures, columns, { pages: 1 }));
    const dax = json.events.filter((e: { name: string }) => e.name === 'Execute DAX Query').map((e: { metrics: { QueryText: string } }) => e.metrics.QueryText);
    expect(dax).toContain('EVALUATE ROW("v", [Margen [%]]])');
    expect(dax.some((q: string) => q.includes("'Tienda''s'[Región]"))).toBe(true);
    expect(dax.every((q: string) => !q.includes("'Hechos'[Importe]")), 'no agrupa por columnas numéricas').toBe(true);
    expect(json.synthetic).toBe(true);
  });

  it('exige medidas o columnas numéricas', () => {
    expect(() => syntheticScenario([], columns.filter((c) => c.dataType === 'Text'))).toThrow(/medidas visibles/);
  });

  it('sin medidas usa SUM de columnas numéricas que no son claves y agrupa por atributos visibles', () => {
    const star = [
      { table: 'Ventas', name: 'Pedido ID', dataType: 'Integer', hidden: true },
      { table: 'Ventas', name: 'Importe', dataType: 'Number', hidden: true },
      { table: 'Ventas', name: 'Cantidad', dataType: 'Integer', hidden: true },
      { table: 'Producto', name: 'Categoría', dataType: 'Text', hidden: false },
      { table: 'Producto', name: 'Código interno', dataType: 'Text', hidden: true },
    ];
    const dax = JSON.parse(syntheticScenario([], star, { pages: 1 })).events
      .filter((e: { name: string }) => e.name === 'Execute DAX Query').map((e: { metrics: { QueryText: string } }) => e.metrics.QueryText);
    expect(dax).toContain(`EVALUATE ROW("v", SUM('Ventas'[Importe]))`);
    expect(dax.some((q: string) => q.includes('Pedido ID'))).toBe(false);
    expect(dax.every((q: string) => !q.includes('Código interno'))).toBe(true);
    expect(dax).toContain(`EVALUATE TOPN(100, SUMMARIZECOLUMNS('Producto'[Categoría], "v", SUM('Ventas'[Cantidad])), [v], DESC)`);
  });

  it('lee las filas de executeQueries de INFO.VIEW', () => {
    const s = parseSchemaRows(
      [{ '[table]': 'Hechos', '[name]': 'Ventas' }],
      [{ '[table]': 'Fecha', '[name]': 'Mes', '[dataType]': 'Text' }, { '[table]': null, '[name]': 'x', '[dataType]': 'Text' }],
    );
    expect(s.measures).toEqual([{ table: 'Hechos', name: 'Ventas' }]);
    expect(s.columns).toEqual([{ table: 'Fecha', name: 'Mes', dataType: 'Text', hidden: false }]);
  });
});
