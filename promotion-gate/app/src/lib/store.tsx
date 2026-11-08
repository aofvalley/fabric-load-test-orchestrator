import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { DEMO_HISTORY, DemoGateService } from './demo';
import { env, missingConfig } from './env';
import type { PhaseStatus } from './gate';
import { setLoginHint, SignInRequiredError } from './msal';
import { rayfinUser } from './rayfinClient';
import { LocalRunStore, openRunStore, type RunStore } from './runs';
import { FabricGateService, type Account, type GateService, type LevelProgress } from './service';
import type { Evidence, JobStatus, RunRecord } from './types';

export type Route = { name: 'new' } | { name: 'runs' } | { name: 'run'; runId: string } | { name: 'settings' };

export interface LiveRun { phases: PhaseStatus[]; levels: LevelProgress[]; failure?: string; updatedAt: number }

interface Gate {
  service: GateService;
  route: Route;
  go(route: Route): void;
  account: Account | null;
  signIn(): Promise<void>;
  authError: string | null;
  missing: string[];
  runs: RunRecord[];
  runsShared: boolean;
  live: Record<string, LiveRun>;
  evidence: Record<string, Evidence>;
  loadEvidence(runId: string, force?: boolean): Promise<Evidence | null>;
  addRun(run: RunRecord): Promise<void>;
  patchRun(runId: string, patch: Partial<RunRecord>): Promise<void>;
}

const Ctx = createContext<Gate | null>(null);

export const ACTIVE: JobStatus[] = ['Locating', 'NotStarted', 'InProgress'];
const FINISHED = ['Completed', 'Failed', 'Cancelled', 'Deduped'];

function parseHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, '');
  if (h.startsWith('run/')) return { name: 'run', runId: decodeURIComponent(h.slice(4)) };
  if (h === 'runs') return { name: 'runs' };
  if (h === 'settings') return { name: 'settings' };
  return { name: 'new' };
}

function toHash(r: Route) {
  return r.name === 'run' ? `#/run/${encodeURIComponent(r.runId)}` : r.name === 'new' ? '#/' : `#/${r.name}`;
}

export function GateProvider({ children }: { children: ReactNode }) {
  const service = useMemo<GateService>(() => (env.demo ? new DemoGateService() : new FabricGateService()), []);
  const [route, setRoute] = useState<Route>(parseHash);
  const [account, setAccount] = useState<Account | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [store, setStore] = useState<RunStore>(() => new LocalRunStore(env.demo ? DEMO_HISTORY : []));
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [live, setLive] = useState<Record<string, LiveRun>>({});
  const [evidence, setEvidence] = useState<Record<string, Evidence>>({});
  const runsRef = useRef(runs);
  runsRef.current = runs;

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const go = useCallback((r: Route) => {
    window.location.hash = toHash(r);
    setRoute(r);
    window.scrollTo({ top: 0 });
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      const s = env.demo ? store : await openRunStore();
      if (!alive) return;
      setStore(s);
      setRuns(await s.list());
      const a = await service.account().catch(() => null);
      if (alive) setAccount(a);
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [service]);

  const signIn = useCallback(async () => {
    setAuthError(null);
    try {
      setLoginHint(rayfinUser().email);
      setAccount(await service.signIn());
    } catch (e) {
      setAuthError((e as Error).message);
    }
  }, [service]);

  const addRun = useCallback(async (run: RunRecord) => {
    const saved = await store.save(run);
    setRuns((rs) => [saved, ...rs.filter((r) => r.run_id !== run.run_id)]);
  }, [store]);

  const patchRun = useCallback(async (runId: string, patch: Partial<RunRecord>) => {
    const current = runsRef.current.find((r) => r.run_id === runId);
    if (!current) return;
    const next = await store.update(current, patch);
    setRuns((rs) => rs.map((r) => (r.run_id === runId ? next : r)));
  }, [store]);

  const loadEvidence = useCallback(async (runId: string, force = false) => {
    if (!force && evidence[runId]?.verdict) return evidence[runId];
    try {
      const ev = await service.evidence(runId);
      setEvidence((m) => ({ ...m, [runId]: ev }));
      return ev;
    } catch {
      return null;
    }
  }, [service, evidence]);

  // Sondeo de los runs activos: localizar el job, avanzar fases y, al terminar, leer el veredicto.
  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      for (const run of runsRef.current.filter((r) => ACTIVE.includes(r.status))) {
        if (stopped) return;
        try {
          let jobId = run.pipeline_job_id;
          if (!jobId) {
            const found = await service.locateJob(run.run_id, new Date(run.started_at));
            if (!found) {
              if (Date.now() - Date.parse(run.started_at) > 10 * 60_000)
                await patchRun(run.run_id, { status: 'Failed', finished_at: new Date().toISOString() });
              continue;
            }
            jobId = found;
            await patchRun(run.run_id, { pipeline_job_id: jobId, status: 'InProgress' });
          }
          const p = await service.progress(jobId, run.run_id, new Date(run.started_at));
          setLive((m) => ({ ...m, [run.run_id]: { phases: p.phases, levels: p.levels, failure: p.failure, updatedAt: Date.now() } }));
          if (FINISHED.includes(p.jobStatus)) {
            const ev = await loadEvidence(run.run_id, true);
            await patchRun(run.run_id, {
              status: p.jobStatus as JobStatus, finished_at: new Date().toISOString(),
              verdict: ev?.verdict?.verdict, promotable: ev?.verdict?.promotable ?? false,
            });
          } else if (run.status !== 'InProgress') {
            await patchRun(run.run_id, { status: 'InProgress' });
          }
        } catch (e) {
          if (e instanceof SignInRequiredError) setAccount(null);
        }
      }
    };
    void tick();
    const id = window.setInterval(tick, env.demo ? 1500 : 15_000);
    return () => { stopped = true; window.clearInterval(id); };
  }, [service, patchRun, loadEvidence]);

  const value: Gate = {
    service, route, go, account, signIn, authError, missing: missingConfig(), runs, runsShared: store.shared,
    live, evidence, loadEvidence, addRun, patchRun,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useGate(): Gate {
  const g = useContext(Ctx);
  if (!g) throw new Error('useGate fuera de GateProvider');
  return g;
}
