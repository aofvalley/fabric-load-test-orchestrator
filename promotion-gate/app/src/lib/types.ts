/** Contratos de las evidencias que escribe el paquete promotion_gate (Python). Solo lectura en la app. */

export type Status = 'PASS' | 'WARN' | 'FAIL' | 'SKIP';
export type Area = 'model_review' | 'load_test' | 'capacity';

export interface Check {
  id: string;
  area: Area;
  status: Status;
  title: string;
  detail: string;
  evidence: Record<string, unknown>;
}

export interface Advice {
  area: Area;
  priority: 1 | 2 | 3;
  title: string;
  action: string;
  evidence: string;
  reference: string;
}

export interface Verdict {
  gate_version: string;
  evaluated_utc: string;
  context: { run_id?: string; dataset?: string; item_id?: string; requested_by?: string; source_ref?: string };
  verdict: 'PASS' | 'WARN' | 'FAIL';
  promotable: boolean;
  areas: Record<Area, Status>;
  counts: Partial<Record<Status, number>>;
  checks: Check[];
  advice: Advice[];
  config: GateConfig;
}

export interface GateConfig {
  model_review: { max_errors: number; max_warnings: number; blocking_rules: string[]; ignored_rules: string[]; sku: string;
    max_model_memory_pct_of_sku: number; max_column_pct_of_model: number };
  load_test: { target_level: number; p50_sec: number; p95_sec: number; max_error_rate: number; max_p95_growth_ratio: number;
    slow_query_sec: number; min_levels: number };
  capacity: { required: boolean; max_utilization_pct: number; warn_interactive_delay_pct: number;
    max_interactive_delay_pct: number; warn_interactive_rejection_pct: number; max_model_failed_operations: number;
    max_tooling_cu_share_pct: number };
  verdict: { warn_blocks_promotion: boolean };
}

export interface Finding {
  rule: string;
  category: string;
  severity: 'Error' | 'Warning' | 'Info';
  object_type: string;
  object_name: string;
  description: string;
  url: string;
}

export interface ModelReview {
  dataset: string;
  item_id?: string;
  error?: string;
  findings?: Finding[];
  vertipaq?: {
    model_size_mb: number | null;
    top_columns: { table: string; column: string; size_mb: number; pct_of_model: number | null; cardinality: number | null; data_type?: string }[];
    top_tables: { table: string; rows: number | null; size_mb: number }[];
  };
}

export interface Level {
  level: number;
  run_id: string;
  users_seen: number;
  queries: number;
  recorded_queries?: number;
  expected_queries: number;
  failed_queries: number;
  errored_queries?: number;
  error_rate: number;
  error_samples: string[];
  mean: number | null;
  p50: number | null;
  p90: number | null;
  p95: number | null;
  p99: number | null;
  max: number | null;
  qps: number | null;
  start_utc: string | null;
  end_utc: string | null;
  duration_s: number;
}

export interface LoadModel {
  model_key: string;
  model: string;
  queries_per_user: number;
  levels: Level[];
  slow_visuals: { visual: string; level: number; count: number; p50: number; p95: number; max: number;
    p95_first_level: number | null; growth: number | null; slow: boolean }[];
  slow_queries: { visual: string; query_number: number; level: number; p95: number; mean: number; rows: number; dax: string }[];
}

export interface LoadTest {
  run_prefix?: string;
  error?: string;
  models: LoadModel[];
  window: { start_utc: string | null; end_utc: string | null };
}

export interface CapacityOp {
  operation: string;
  cu_s: number;
  duration_s: number;
  operations: number;
  failed: number;
  rejected: number;
  throttling_min: number;
  cu_s_per_operation: number | null;
}

export interface Capacity {
  error?: string;
  version?: string;
  capacity_id?: string;
  timepoints_in_window?: number;
  covers_window_end?: boolean;
  peak_utilization_pct?: number;
  avg_utilization_pct?: number;
  peak_interactive_delay_pct?: number;
  peak_interactive_rejection_pct?: number;
  peak_background_rejection_pct?: number;
  peak_carryover_pct?: number;
  model?: { item_id: string; found: boolean; cu_s: number; failed_operations: number; rejected_operations: number;
    throttling_min: number; operations: CapacityOp[] };
  tooling?: { workspace_id: string | null; cu_s: number; share_pct: number };
}

export interface Evidence {
  verdict: Verdict | null;
  review: ModelReview | null;
  loadtest: LoadTest | null;
  capacity: Capacity | null;
  report: string | null;
}

/** Fila de historial (entidad GateRun de Rayfin o localStorage en local/demo). */
export interface RunRecord {
  id?: string;
  run_id: string;
  user_id: string;
  requested_by: string;
  workspace_id: string;
  workspace_name: string;
  dataset_id: string;
  dataset_name: string;
  report_id?: string;
  report_name?: string;
  model_key: string;
  scenario_path: string;
  scenario_source: 'upload' | 'existing' | 'synthetic';
  ramp_levels: string;
  target_level: number;
  gate_config_json?: string;
  pipeline_job_id: string;
  status: JobStatus;
  verdict?: 'PASS' | 'WARN' | 'FAIL';
  promotable?: boolean;
  started_at: string;
  finished_at?: string;
  promoted_at?: string;
  promoted_by?: string;
  promoted_to?: string;
}

export type JobStatus = 'Locating' | 'NotStarted' | 'InProgress' | 'Completed' | 'Failed' | 'Cancelled' | 'Deduped';
