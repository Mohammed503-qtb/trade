/** عقود اللوحة — مرآة TypeScript لعقود schemas (§35.2 + §35.3 + §31.6). */

export interface PanelField {
  key: string;
  value: string;
  detail: string | null;
}

export interface ReasoningTrace {
  scenario_id: string;
  template: string;
  direction: string;
  why_active: string[];
  what_against: string[];
  why_wait: string[];
}

export interface ScenarioView {
  scenario_id: string;
  template: string;
  direction: string;
  state: string;
  created_time: string;
  trigger_status: string;
  entry_price_low: number;
  entry_price_high: number;
  stop: number;
  target_price: number;
  evidence_count: number;
  score: number;
}

export interface RejectionView {
  decision_id: string;
  scenario_id: string | null;
  reason_code: string;
  explanation: string;
  as_of: string;
}

export interface ExecutionView {
  mode: string;
  trades_count: number;
  net_expectancy_r: number;
  profit_factor: number | null;
  win_rate: number;
  report_ref: string;
}

export interface WebhookEventView {
  alert_key: string;
  instrument: string;
  event: string;
  status: string;
  received_at: string;
}

export interface DashboardCounts {
  risk_decisions: number;
  authorized: number;
  rejected: number;
  simulated_trades: number;
  active_scenarios: number;
}

export interface DashboardOverview {
  panel: PanelField[];
  traces: ReasoningTrace[];
  scenarios: ScenarioView[];
  rejections: RejectionView[];
  execution: ExecutionView;
  alerts: WebhookEventView[];
  counts: DashboardCounts;
  composition_ref: string;
}

export interface AlertRecord {
  alert_key: string;
  instrument: string;
  event: string;
  timeframe: string;
  price: number;
  status: string;
  received_at: string;
  processed_at: string | null;
  processing_result: { matched?: boolean; detail?: string } | null;
}
