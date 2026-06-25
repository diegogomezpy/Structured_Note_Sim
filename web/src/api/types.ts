/* Shapes returned by the FastAPI backend (api/main.py + api/engine.py). */

export interface ConfigMeta {
  file: string
  name: string
  issuer: string
}

export interface UnderlyingOption {
  label: string
  symbol: string
}

/** NoteTerms.to_dict() payload. Optional fields kept loose — only the ones the
    UI reads/edits are typed; the rest round-trip untouched on simulate. */
export type Basket = 'worst_of' | 'best_of' | 'average'

export interface NoteTerms {
  name: string
  issuer: string
  maturity: number
  payment_freq: 'monthly' | 'quarterly' | 'semi-annual' | 'annual'
  coupon_pa: number
  coupon_barrier: number
  autocall_barrier: number
  autocall_start_period: number
  knock_in_barrier: number
  memory: boolean
  coupon_basket: Basket
  autocall_basket: Basket
  one_star_level: number | null
  // advanced / optional payoff fields (always present after NoteTerms.to_dict)
  autocall_step_down: number | null
  autocall_floor: number | null
  coupon_at_autocall_only: boolean
  capital_guarantee: number
  upside_cap: number | null
  principal_protection: number
  // metadata
  issuer_description: string
  issuer_rating_sp: string
  issuer_rating_moody: string
  issuer_rating_fitch: string
  tickers: Record<string, string>
  issue_date: string | null
  underlyings: Record<string, UnderlyingOverride> | null
  [k: string]: unknown
}

export interface HestonParam {
  name: string
  S0: number | null
  mu: number | null
  V0: number | null
  theta: number | null
  kappa: number | null
  xi: number | null
  rho: number | null
  feller: number | null
}

export interface SimSummary {
  expected_irr: number | null
  expected_total_return: number | null
  expected_coupon: number | null
  prob_autocall: number | null
  prob_knock_in_total: number | null
  prob_maturity: number | null
  prob_rescued: number | null
  prob_barrier_event: number | null
  expected_nominal_payout: number | null
  loss_given_knock_in: number | null
  coupon_pa: number | null
  n_obs: number
  n_paths: number
  engine: string
  assets: string[]
  autocall_by_period: number[]
  obs_times: number[]
  t_dof: number | null
  calibration: HestonParam[]
}

export interface AssetFan {
  name: string
  fig: any
}

export interface SimFigures {
  irr_dist: any
  wof_fan: any
  asset_fans: AssetFan[]
  corr_input: any
  corr_realized: any
  corr_diff: any
}

export interface SimResult {
  run_id: string
  summary: SimSummary
  figures: SimFigures
}

export interface SimulateRequest {
  terms: NoteTerms
  n_paths?: number
  seed?: number
  calib_years?: number
  history_years?: number | null
  engine?: 'numpy' | 'cpp'
  lang?: 'en' | 'es'
}

/** Optional issue-date window for the backtest (ISO dates, null = unbounded). */
export interface BtRange { start: string | null; end: string | null }

export interface BacktestIssue {
  issue_date: string
  call_quarter: number
  knock_in: boolean
  irr: number | null
  worst_asset: string
  worst_perf: number | null
}

export interface BacktestSummary {
  n_issues: number
  mean_irr: number | null
  median_irr: number | null
  prob_called: number | null
  prob_knock_in: number | null
  prob_maturity: number | null
  loss_given_knock_in: number | null
  [k: string]: number | null
}

export interface BacktestFigures {
  worst_asset_pie: any
  irr_scatter: any
  prices: any
}

export interface BacktestResult {
  summary: BacktestSummary
  issues: BacktestIssue[]
  figures: BacktestFigures | null
}

export interface ExplorerPath {
  wof: number[]
  ap: number       // autocall period (0 = none)
  ki: boolean
  irr: number | null
  issue_date?: string   // backtest explorer only — the historical issue date
}

export interface ExplorerData {
  t: number[]
  paths: ExplorerPath[]
  n_total: number
  obs_times: number[]
  barriers: { knock_in: number | null; autocall: number | null; coupon: number | null }
}

export type LiveStatus = 'autocalled' | 'coupon_paid' | 'coupon_missed' | 'no_coupon' | 'upcoming'

export interface LiveSummary {
  issue_date: string
  anchor_date: string
  maturity_date: string
  today: string
  history_gap_days: number
  elapsed_years: number | null
  remaining_years: number | null
  pct_elapsed: number | null
  wof_today: number | null
  worst_asset: string
  worst_symbol: string
  ki_buffer: number | null
  ac_buffer: number | null
  next_ac_barrier: number | null
  knock_in_barrier: number | null
  coupon_barrier: number | null
  coupon_rate: number | null
  coupon_pa: number | null
  total_coupons: number | null
  pending_coupons: number
  pending_value: number | null
  irr_to_date: number | null
  autocall_period: number
  alive: boolean
  coupon_at_autocall_only: boolean
  next_premium: number | null
}

export interface LiveAsset {
  name: string
  symbol: string
  perf: number | null
}

export interface LiveObsRow {
  period: string
  date: string | null
  status: LiveStatus
  wof: number | null
  coupon: number | null
  cumulative: number | null
  upcoming: boolean
}

export interface LiveResult {
  available: boolean
  reason?: 'no_issue_date' | 'not_issued' | 'not_enough_data'
  summary?: LiveSummary
  assets?: LiveAsset[]
  obs_rows?: LiveObsRow[]
  figure?: any
}

export type Sentiment = 'buy' | 'hold' | 'sell'

/** Analyst recommendation split — % of analysts rating buy / hold / sell. */
export interface AnalystSplit { buy: number; hold: number; sell: number }

/** Per-underlying overrides stored on terms.underlyings, keyed by display name. */
export interface UnderlyingOverride {
  description?: string
  logo?: string          // data-URL (base64) custom logo
  analyst?: AnalystSplit | null
}

export interface DescribeResult {
  issuer_description: string | null
  underlyings: Record<string, string | null>   // keyed by yfinance symbol
}

export interface UnderlyingMetric {
  name: string
  symbol: string
  long_name: string
  type: string | null
  sector: string | null
  market_cap: number | null
  iv_3m: number | null
  iv_source: string | null
  last_price: number | null
  rsi_14: number | null
  business_summary: string | null
  figure: any
}

export interface InspectFilters {
  outcome?: 'any' | 'autocalled' | 'maturity' | 'loss'
  ac_periods?: number[]
  ki_choice?: 'any' | 'yes' | 'no'
  ret_lo?: number | null
  ret_hi?: number | null
  coupon_periods?: number[]
}

export interface PathMarker { x: number; y: number; text: string; kind: string }

export interface PathData {
  t: number[]
  series: { name: string; perf: number[] }[]
  wof: number[]
  markers: PathMarker[]
  x_max: number
  barriers: { knock_in: number | null; autocall: number | null; autocall_schedule: [number, number][] | null }
}

export interface InspectResult {
  n_total: number
  n_matched: number
  ret_range: [number, number]
  n_obs: number
  coupon_available: boolean
  position: number
  path_index: number | null
  path?: PathData
  outcome?: { autocall_q: number; call_time: number | null; knock_in: boolean; worst_final: number | null }
  metrics?: { principal: number | null; coupons: number | null; irr: number | null; total_return: number | null }
  assets?: { name: string; final: number | null }[]
}

/** Firm-branding overrides for the PDF (subset of pdf_report's schema). */
export interface Branding {
  firm_name?: string
  report_title?: string
  primary_color?: string
  accent_color?: string
  chart_secondary_color?: string
  section_rule_color?: string
  panel_color?: string
  website?: string
  contact?: string
  footer_note?: string
  disclaimer_body?: string
  logo_base64?: string
  [k: string]: unknown        // presets carry extra keys we pass straight through
}

export interface ReportRequest {
  terms: NoteTerms
  sections: string[]          // fine include keys; empty = everything
  lang?: 'en' | 'es'
  n_paths?: number
  seed?: number
  calib_years?: number
  engine?: 'numpy' | 'cpp'
  branding?: Branding | null
}

export interface Health {
  status: string
  cpp_engine: boolean
}

export interface LogoData {
  map: Record<string, string>
  base: string // URL template containing "{sym}"
  issuers: Record<string, string>
}
