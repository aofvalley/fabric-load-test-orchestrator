import { History as HistoryIcon, LogIn, Plus, Settings as SettingsIcon } from 'lucide-react';
import { ACTIVE, GateProvider, useGate } from './lib/store';
import { History } from './views/History';
import { NewGate } from './views/NewGate';
import { RunView } from './views/RunView';
import { Settings } from './views/Settings';

function Mark() {
  return (
    <svg className="rail__mark" viewBox="0 0 34 34" aria-hidden>
      <path d="M8 4h18l4 5v21H4V9z" fill="#2f8f5b" />
      <circle cx="17" cy="9" r="2.6" fill="#15233f" />
      <path d="M10 18h14M10 22.5h14M10 27h8" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" opacity="0.9" />
    </svg>
  );
}

function Shell() {
  const { route, go, runs, account, signIn, service } = useGate();
  const active = runs.filter((r) => ACTIVE.includes(r.status)).length;
  const at = (n: string) => (route.name === n || (n === 'runs' && route.name === 'run') ? 'page' : undefined);

  return (
    <div className="shell">
      <nav className="rail" aria-label="Principal">
        <div className="rail__brand">
          <Mark />
          <div className="rail__name">Gate de promoción<small>Modelos semánticos a producción</small></div>
        </div>
        <div className="rail__nav">
          <button aria-current={at('new')} onClick={() => go({ name: 'new' })}><Plus size={18} aria-hidden />Nuevo gate</button>
          <button aria-current={at('runs')} onClick={() => go({ name: 'runs' })}>
            <HistoryIcon size={18} aria-hidden />Runs
            {active ? <><span className="live" aria-hidden /><span className="sr-only">{active} en curso</span></> : <span className="count">{runs.length}</span>}
          </button>
          <button aria-current={at('settings')} onClick={() => go({ name: 'settings' })}><SettingsIcon size={18} aria-hidden />Ajustes</button>
        </div>
        <div className="rail__foot">
          {service.demo && <span className="rail__demo">Datos sintéticos</span>}
          {account ? (
            <div className="rail__who" title={account.username}>{account.name}<small>{account.username}</small></div>
          ) : (
            <button className="btn btn--quiet" style={{ color: 'var(--rail-ink)', justifyContent: 'flex-start', padding: '6px 0' }} onClick={signIn}>
              <LogIn size={16} aria-hidden />Iniciar sesión
            </button>
          )}
        </div>
      </nav>
      <main className="main" id="main">
        {route.name === 'new' && <NewGate />}
        {route.name === 'runs' && <History />}
        {route.name === 'run' && <RunView key={route.runId} runId={route.runId} />}
        {route.name === 'settings' && <Settings />}
      </main>
    </div>
  );
}

export function App() {
  return <GateProvider><Shell /></GateProvider>;
}
