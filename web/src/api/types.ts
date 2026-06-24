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
  coupon_basket: string
  autocall_basket: string
  one_star_level: number | null
  tickers: Record<string, string>
  issue_date: string | null
  underlyings: string[] | null
  [k: string]: unknown
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

export interface BacktestResult {
  summary: BacktestSummary
  issues: BacktestIssue[]
}

export interface ExplorerPath {
  wof: number[]
  ap: number       // autocall period (0 = none)
  ki: boolean
  irr: number | null
}

export interface ExplorerData {
  t: number[]
  paths: ExplorerPath[]
  n_total: number
  obs_times: number[]
  barriers: { knock_in: number | null; autocall: number | null; coupon: number | null }
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
