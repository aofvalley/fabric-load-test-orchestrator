import { CircleCheck, TriangleAlert } from 'lucide-react';
import { useEffect, useState } from 'react';
import { env } from '../lib/env';
import { num } from '../lib/format';
import { SCOPES } from '../lib/msal';
import { useGate } from '../lib/store';
import type { GateConfig } from '../lib/types';

export function Settings() {
  const { service, account, signIn, missing, runsShared, authError } = useGate();
  const [team, setTeam] = useState<Partial<GateConfig> | null | undefined>(undefined);

  useEffect(() => {
    if (!account) return;
    service.teamConfig().then(setTeam).catch(() => setTeam(null));
  }, [account, service]);

  const row = (label: string, value: string, ok = true) => (
    <tr><td className="label" style={{ width: 260 }}>{label}</td><td className={ok ? 'mono' : 'mono'} style={{ fontSize: 12, color: ok ? undefined : 'var(--fail)' }}>{value || 'sin definir'}</td></tr>
  );

  return (
    <>
      <header className="page-head">
        <div><h1>Ajustes y conexión</h1><p>De dónde lee y dónde lanza la app. Se configura en el .env antes de desplegar con Rayfin.</p></div>
      </header>

      <div className="stack">
        <section className="sheet" style={{ padding: 'var(--sp-5)' }}>
          <div className="section-title"><h3>Conexión</h3></div>
          {service.demo ? (
            <div className="notice notice--warn"><TriangleAlert aria-hidden /><div><strong>Modo demostración</strong><p>Todos los datos son sintéticos (tools/make_demo_evidence.py). Nada se lanza en Fabric.</p></div></div>
          ) : missing.length ? (
            <div className="notice notice--fail"><TriangleAlert aria-hidden /><div><strong>Configuración incompleta</strong><p>Falta {missing.join(', ')}.</p></div></div>
          ) : (
            <div className="notice notice--ok"><CircleCheck aria-hidden /><div><strong>Configuración completa</strong><p>{account ? `Sesión de Fabric como ${account.username}.` : 'Inicia sesión para comprobar los permisos.'}</p></div></div>
          )}
          <div className="table-wrap" style={{ marginTop: 'var(--sp-4)' }}>
            <table className="table">
              <tbody>
                {row('Workspace del gate', env.gateWorkspaceId, !!env.gateWorkspaceId || service.demo)}
                {row('Lakehouse del gate', env.gateLakehouseId, !!env.gateLakehouseId || service.demo)}
                {row('Workspace de Capacity Metrics', env.capacityMetricsWorkspace, true)}
                {row('Registro de aplicación (MSAL)', env.msalClientId, !!env.msalClientId || service.demo)}
                {row('Historial', runsShared ? 'Base de datos de la app (Rayfin)' : 'Este navegador', true)}
              </tbody>
            </table>
          </div>
          {!account && <button className="btn btn--primary" style={{ marginTop: 'var(--sp-4)' }} onClick={signIn}>Iniciar sesión en Fabric</button>}
          {authError && <p className="field__error">{authError}</p>}
        </section>

        <section className="sheet" style={{ padding: 'var(--sp-5)' }}>
          <div className="section-title"><h3>Umbrales del equipo</h3><span>Files/PromotionGate/config/gate.yaml, solo lectura</span></div>
          {team === undefined ? <p className="field__hint">{account ? 'Leyendo…' : 'Inicia sesión para leerlos.'}</p> : !team ? <p className="field__hint">No hay gate.yaml en el lakehouse: el gate usa los valores por defecto del paquete.</p> : (
            <div className="grid-3">
              <dl className="stack" style={{ margin: 0 }}>
                <dt className="label">Test de carga</dt>
                <dd style={{ margin: 0 }}>Usuarios objetivo {team.load_test?.target_level}<br />p95 ≤ {num(team.load_test?.p95_sec, 1)} s, p50 ≤ {num(team.load_test?.p50_sec, 1)} s<br />Errores ≤ {num((team.load_test?.max_error_rate ?? 0) * 100)} %</dd>
              </dl>
              <dl className="stack" style={{ margin: 0 }}>
                <dt className="label">Buenas prácticas</dt>
                <dd style={{ margin: 0 }}>Errores BPA ≤ {team.model_review?.max_errors}, avisos ≤ {team.model_review?.max_warnings}<br />SKU {team.model_review?.sku}<br />Reglas bloqueantes: {team.model_review?.blocking_rules?.length ?? 0}</dd>
              </dl>
              <dl className="stack" style={{ margin: 0 }}>
                <dt className="label">Capacity Metrics</dt>
                <dd style={{ margin: 0 }}>Utilización ≤ {team.capacity?.max_utilization_pct} %<br />Retraso interactivo &lt; {team.capacity?.max_interactive_delay_pct} %<br />{team.capacity?.required ? 'Obligatorio' : 'Opcional'}</dd>
              </dl>
            </div>
          )}
        </section>

        <section className="sheet" style={{ padding: 'var(--sp-5)' }}>
          <div className="section-title"><h3>Permisos delegados que pide la app</h3><span>Consentimiento incremental: cada grupo la primera vez que hace falta</span></div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Para qué</th><th>Scopes</th></tr></thead>
              <tbody>
                {([['Descubrir workspaces y modelos', 'fabricRead'], ['Lanzar y seguir el gate', 'fabricRun'], ['Promocionar con deployment pipelines', 'fabricDeploy'],
                  ['Informes y escenario sintético', 'powerbi'], ['Escenarios y evidencias en OneLake', 'onelake']] as [string, keyof typeof SCOPES][]).map(([l, k]) => (
                  <tr key={k}><td>{l}</td><td className="mono" style={{ fontSize: 12 }}>{SCOPES[k].map((s) => s.replace(/^https:\/\/[^/]+\//, '')).join(', ')}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}
