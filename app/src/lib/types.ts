export type Role = "user" | "assistant" | "system";

export interface Provider {
  id: string;
  name: string;
  kind: "openai" | "anthropic" | "google" | "azure" | string;
  base_url: string;
  model: string;
  models: string[];
  headers: Record<string, string>;
  enabled: boolean;
  is_default: boolean;
  has_key: boolean;
  key_hint: string;
  last_status: string;
  last_latency_ms: number;
  last_checked: number;
}

export interface McpTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface McpServer {
  id: string;
  name: string;
  transport: "stdio" | "http" | string;
  command: string;
  args: string[];
  url: string;
  env: Record<string, string>;
  enabled: boolean;
  auto_start: boolean;
  category: string;
  notes: string;
  status: "running" | "stopped" | "error" | string;
  error: string;
  tool_count: number;
  tools: McpTool[];
}

export interface McpCatalogItem {
  id: string;
  name: string;
  transport: string;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  category: string;
  notes: string;
  installed: boolean;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  path: string;
  enabled: boolean;
  source: string;
  size: number;
  preview: string;
}

export interface Account {
  id: string;
  name: string;
  broker: string;
  environment: string;
  config: Record<string, unknown>;
  enabled: boolean;
  status: string;
  last_error: string;
  has_secret: boolean;
  created_at: number;
  snapshot?: Record<string, unknown>;
}

export interface BrokerField {
  key: string;
  label: string;
  type: string;
  options?: string[];
  default?: string | number;
  placeholder?: string;
  secret?: boolean;
}

export interface BrokerCatalogItem {
  id: string;
  label: string;
  tagline: string;
  environments: string[];
  fields: BrokerField[];
  docs: string;
}

export interface Settings {
  trading_mode: string;
  allow_live_trading: boolean;
  require_order_approval: boolean;
  kill_switch: boolean;
  max_risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  max_open_positions: number;
  max_lot_size: number;
  max_spread_points: number;
  default_symbols: string[];
  auto_execute_tools: boolean;
  autopilot_enabled?: boolean;
  autopilot_autostart?: boolean;
  autopilot_interval_sec?: number;
  autopilot_symbols?: string[];
  autopilot_symbols_per_cycle?: number;
  autopilot_provider_ids?: string[];
  autopilot_execution?: "auto" | "approval" | string;
  autopilot_confidence?: number;
  autopilot_max_trades_per_day?: number;
  autopilot_sl_atr?: number;
  autopilot_tp_atr?: number;
  autopilot_cooldown_sec?: number;
  autopilot_allow_live_auto?: boolean;
  default_account_id?: string;
  theme?: string;
  [key: string]: unknown;
}

export interface SystemInfo {
  app: string;
  version: string;
  platform: string;
  machine: string;
  python: string;
  home: string;
  data_dir: string;
  skills_dir: string;
  vault: string;
  host: string;
  port: number;
  mt5_available: boolean;
  node: boolean;
  uv: boolean;
}

export interface Bootstrap {
  system: SystemInfo;
  settings: Settings;
  providers: Provider[];
  mcp: McpServer[];
  skills: Skill[];
  accounts: Account[];
  broker_catalog: BrokerCatalogItem[];
  conversations: Conversation[];
  approvals: Approval[];
}

export interface Conversation {
  id: string;
  title: string;
  model: string;
  created_at: number;
  updated_at: number;
}

export interface Message {
  id?: string;
  role: Role;
  content: string;
  created_at?: number;
  meta?: { trace?: ToolTrace[] };
  trace?: ToolTrace[];
  streaming?: boolean;
}

export interface ToolTrace {
  name: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface Order {
  id: string;
  account_id: string;
  symbol: string;
  side: string;
  volume: number;
  order_type: string;
  price: number;
  sl: number;
  tp: number;
  status: string;
  risk_usd: number;
  risk_pct: number;
  reason: string;
  ticket: string;
  broker_response: string;
  created_at: number;
  pnl: number;
}

export interface Position {
  ticket: string;
  account_id?: string;
  symbol: string;
  side: string;
  volume: number;
  entry: number;
  price?: number;
  sl?: number;
  tp?: number;
  pnl: number;
  status?: string;
  broker?: string;
}

export interface Approval {
  id: string;
  kind: string;
  payload_json: string;
  status: string;
  created_at: number;
  result_json?: string;
}

export interface RiskCheck {
  ok: boolean;
  label: string;
  detail: string;
}

export interface ChatEvent {
  type: "text" | "tool_start" | "tool_result" | "error" | "done";
  text?: string;
  name?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  message?: string;
  conversation_id?: string;
  trace?: ToolTrace[];
}

export interface AutopilotStatus {
  running: boolean;
  stage: string;
  symbol: string;
  cycle: number;
  started_at: number;
  last_cycle_at: number;
  next_run_at: number;
  last_error: string;
  halted_reason: string;
  using_models: string[];
  last_decision: {
    symbol: string;
    action: string;
    confidence: number;
    status: string;
    reason: string;
    ts: number;
  } | null;
}

export interface DecisionVote {
  provider_id?: string;
  name?: string;
  model?: string;
  ok: boolean;
  action: string;
  confidence: number;
  reason: string;
  sl_atr?: number;
  tp_atr?: number;
  latency_ms?: number;
  error?: string;
}

export interface Decision {
  id: string;
  ts: number;
  account_id: string;
  symbol: string;
  action: string;
  confidence: number;
  price: number;
  reason: string;
  model: string;
  status: string;
  order_id: string;
  risk_usd: number;
  pnl: number;
  votes: DecisionVote[];
  snapshot: Record<string, unknown>;
}

export interface EquityPoint {
  ts: number;
  equity: number;
}

export interface DashboardStats {
  closed_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  today_pnl: number;
  profit_factor: number;
  trades_today: number;
}

export interface DashboardPayload {
  autopilot: AutopilotStatus;
  control: Record<string, unknown>;
  account: {
    id: string;
    name: string;
    broker: string;
    environment: string;
    snapshot: Record<string, unknown>;
  };
  positions: Position[];
  stats: DashboardStats;
  decisions: Decision[];
  closed_positions: Record<string, unknown>[];
  orders: Order[];
  equity: EquityPoint[];
  activity: { ts: number; actor: string; action: string; detail: string }[];
}
