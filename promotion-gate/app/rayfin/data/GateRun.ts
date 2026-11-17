import { entity, role, uuid, text, int, boolean, date } from '@microsoft/rayfin-core';

/**
 * Un run del gate lanzado desde la app. Es un puntero: la evidencia vive en el lakehouse del gate
 * (Files/PromotionGate/runs/<run_id>/) y la auditoría oficial en las tablas Delta gate_runs y gate_checks.
 * Todos los usuarios autenticados ven el historial del equipo y pueden crear runs; solo el autor edita el suyo.
 */
@entity()
@role('authenticated', ['read', 'create'])
@role('authenticated', 'update', { policy: (claims: any, item: any) => claims.sub.eq(item.user_id) })
export class GateRun {
  @uuid() id!: string;
  /** Número de certificado visible, p. ej. GATE-20261105-0930-4F2A. */
  @text() run_id!: string;
  @text() user_id!: string;
  @text() requested_by!: string;

  @text() workspace_id!: string;
  @text() workspace_name!: string;
  @text() dataset_id!: string;
  @text() dataset_name!: string;
  @text({ optional: true }) report_id?: string;
  @text({ optional: true }) report_name?: string;
  @text() model_key!: string;
  @text() scenario_path!: string;
  /** upload | existing | synthetic */
  @text() scenario_source!: string;

  @text() ramp_levels!: string;
  @int() target_level!: number;
  @text({ optional: true }) gate_config_json?: string;

  @text({ optional: true }) pipeline_job_id?: string;
  /** Locating | NotStarted | InProgress | Completed | Failed | Cancelled */
  @text() status!: string;
  /** PASS | WARN | FAIL, cuando existe verdict.json */
  @text({ optional: true }) verdict?: string;
  @boolean({ optional: true }) promotable?: boolean;

  @date() started_at!: Date;
  @date({ optional: true }) finished_at?: Date;
  @date({ optional: true }) promoted_at?: Date;
  @text({ optional: true }) promoted_by?: string;
  @text({ optional: true }) promoted_to?: string;
}
