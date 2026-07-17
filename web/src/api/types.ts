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
  // One-Star scope: the best-of rescue always applies to final redemption; these
  // extend it to the periodic coupon / autocall checks (off by default).
  one_star_coupon?: boolean
  one_star_autocall?: boolean
  // advanced / optional payoff fields (always present after NoteTerms.to_dict)
  autocall_step_down: number | null
  autocall_floor: number | null
  coupon_at_autocall_only: boolean
  // Zenith effect: uncapped worst-of upside participation on an in-the-money
  // redemption (autocall, or maturity >= 100%) — see core/note.py:price_note.
  zenith?: boolean
  capital_guarantee: number
  upside_cap: number | null
  principal_protection: number
  // structure type — drives which menu / payoff / diagram applies
  note_type: 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'
  // Participation Note (note_type === 'participation'): one downside + one upside style
  participation_downside?: 'full' | 'buffer' | 'airbag' | 'bear'
  participation_upside?: 'linear' | 'shark_fin' | 'digital'
  participation_basket?: Basket
  protection_level?: number
  participation_rate?: number
  participation_strike?: number
  knockout_level?: number | null
  knockout_payout?: number
  digital_payout?: number
  // Periodic / cliquet mode — participation paid each reset period (floored at 0)
  participation_periodic?: boolean
  period_cap?: number | null
  // metadata
  note_description: string
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
  avg_time_to_autocall: number | null
  coupon_pa: number | null
  n_obs: number
  n_paths: number
  engine: string
  assets: string[]
  autocall_by_period: number[]
  obs_times: number[]
  t_dof: number | null
  calibration: HestonParam[]
  // structure type + participation-only metrics (null/absent on Phoenix)
  note_type?: 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'
  prob_above_par?: number | null
  prob_below_par?: number | null
  prob_at_cap?: number | null
  prob_knocked_out?: number | null
  expected_gain?: number | null
  expected_redemption?: number | null
  p5_redemption?: number | null
  p95_redemption?: number | null
  cvar5_redemption?: number | null
  breakeven_level?: number | null
  up_capture?: number | null
  dn_capture?: number | null
  // Downsampled final-basket levels (participation runs only) — powers the payoff
  // diagram's distribution overlay and the client-side what-if recompute.
  final_basket_sample?: number[]
  // Cliquet per-reset stats — power the per-period small-multiples.
  period_move_mean?: number[]
  period_income_mean?: number[]
  period_move_p25?: number[]
  period_move_p75?: number[]
}

export interface AssetFan {
  name: string
  fig: any
}

export interface SimFigures {
  outcome: any
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

// ── A/B comparison ────────────────────────────────────────────────────────────
export interface CompareDiffRow {
  key: string
  a: number | null
  b: number | null
  delta: number | null
}
export interface CompareDiff {
  rows: CompareDiffRow[]
  both_participation: boolean
}
export interface CompareResult {
  a: SimResult
  b: SimResult
  compare: {
    shared_paths: boolean
    diff: CompareDiff
    figures: { irr: any; outcome: any }
  }
}

/** Optional issue-date window for the backtest (ISO dates, null = unbounded). */
export interface BtRange { start: string | null; end: string | null }

export interface BacktestIssue {
  issue_date: string
  call_quarter?: number
  knock_in?: boolean
  irr: number | null
  worst_asset: string
  worst_perf: number | null
  // participation
  redemption?: number | null
  income?: number | null       // cliquet participation income (can be negative)
  band?: string                // realised-redemption band label
}

export interface BacktestSummary {
  n_issues: number
  mean_irr: number | null
  median_irr: number | null
  prob_called: number | null
  prob_knock_in: number | null
  prob_maturity: number | null
  loss_given_knock_in: number | null
  avg_time_to_autocall: number | null
  expected_total_return?: number | null
  expected_coupon?: number | null
  // participation
  expected_redemption?: number | null
  median_redemption?: number | null
  best_redemption?: number | null
  worst_redemption?: number | null
  prob_above_par?: number | null
  prob_below_par?: number | null
  cvar5_redemption?: number | null
  note_type?: 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'
  participation_periodic?: boolean
}

export interface BacktestFigures {
  worst_asset_pie: any
  irr_scatter: any
  prices: any
  redemption_dist?: any   // participation only
}

export interface BacktestResult {
  summary: BacktestSummary
  issues: BacktestIssue[]
  figures: BacktestFigures | null
  note_type?: 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'
}

/** Participation payoff reference levels carried on fan / inspector barriers. */
export interface PartBarriers {
  strike: number | null
  floor: number | null
  cap: number | null
  periodic: boolean
}

export interface ExplorerPath {
  wof: number[]
  ap: number       // autocall period (0 = none)
  ki: boolean
  irr: number | null
  red?: number | null   // participation: realised redemption (fraction of par)
  issue_date?: string   // backtest explorer only — the historical issue date
}

export interface ExplorerData {
  t: number[]
  paths: ExplorerPath[]
  n_total: number
  note_type?: 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'
  obs_times: number[]
  barriers: { knock_in?: number | null; autocall?: number | null; coupon?: number | null
              participation?: PartBarriers }
}

export type LiveStatus = 'autocalled' | 'coupon_paid' | 'coupon_missed' | 'no_coupon' | 'upcoming'
  | 'part_gain' | 'part_loss' | 'part_flat' | 'running'

export interface LiveSummary {
  issue_date: string
  anchor_date: string
  maturity_date: string
  today: string
  history_gap_days: number
  elapsed_years: number | null
  remaining_years: number | null
  pct_elapsed: number | null
  wof_today?: number | null
  worst_asset: string
  worst_symbol: string
  // phoenix
  ki_buffer?: number | null
  ac_buffer?: number | null
  next_ac_barrier?: number | null
  knock_in_barrier?: number | null
  coupon_barrier?: number | null
  coupon_rate?: number | null
  coupon_pa?: number | null
  total_coupons?: number | null
  pending_coupons?: number
  pending_value?: number | null
  irr_to_date?: number | null
  autocall_period?: number
  alive: boolean
  coupon_at_autocall_only?: boolean
  next_premium?: number | null
  // participation
  note_type?: 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'
  participation_periodic?: boolean
  participation_basket?: Basket
  basket_today?: number | null
  projected_redemption?: number | null
  projected_gain?: number | null
  redeem_now?: number | null
  strike?: number | null
  breakeven_level?: number | null
  dist_breakeven?: number | null
  protection_level?: number | null
  dist_protection?: number | null
  cap_level?: number | null
  dist_cap?: number | null
  accrued_income?: number | null
  current_income?: number | null
  n_reset_done?: number | null
  n_reset_total?: number | null
  period_cap?: number | null
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
  wof?: number | null
  coupon?: number | null
  cumulative?: number | null
  upcoming: boolean
  // participation cliquet
  move?: number | null
  income?: number | null
}

export interface LiveResult {
  available: boolean
  reason?: 'no_issue_date' | 'not_issued' | 'not_enough_data' | 'participation_pdf_unsupported'
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

/** Overlapping price history available for a ticker set (/api/history) — the cap
    the calibration-window control offers. `years` 0 = unknown / nothing resolved. */
export interface HistorySpan {
  years: number
  start: string | null
  end: string | null
  n_days: number
}

export interface UnderlyingMetric {
  name: string
  symbol: string
  long_name: string
  type: string | null
  sector: string | null
  industry?: string | null
  sector_key?: string | null   // resolved cover-photo sector (industry-first)
  market_cap: number | null
  iv_3m: number | null
  iv_source: string | null
  last_price: number | null
  day_change: number | null
  rsi_14: number | null
  business_summary: string | null
  figure: any
}

/** Fast quote snapshot from /api/quotes (fast_info only) — drives the live ticker
    tape and its hover detail card. Every field is best-effort and may be null. */
export interface Quote {
  price: number | null
  change: number | null
  open: number | null
  prev_close: number | null
  day_low: number | null
  day_high: number | null
  year_low: number | null
  year_high: number | null
  volume: number | null
  market_cap: number | null
  currency: string | null
}

export interface InspectFilters {
  outcome?: 'any' | 'autocalled' | 'maturity' | 'loss' | 'part_gain' | 'part_par' | 'part_loss'
  ac_periods?: number[]
  ki_choice?: 'any' | 'yes' | 'no'
  ret_lo?: number | null
  ret_hi?: number | null
  coupon_periods?: number[]
}

export interface PathMarker { x: number; y: number; text: string; kind: string; n?: number }

export interface PathData {
  t: number[]
  series: { name: string; perf: number[] }[]
  wof: number[]
  markers: PathMarker[]
  x_max: number
  barriers: { knock_in?: number | null; autocall?: number | null
              autocall_schedule?: [number, number][] | null
              participation?: PartBarriers }
}

export interface InspectResult {
  n_total: number
  n_matched: number
  ret_range: [number, number]
  n_obs: number
  coupon_available: boolean
  note_type?: 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'
  participation_periodic?: boolean
  position: number
  path_index: number | null
  path?: PathData
  outcome?: { autocall_q: number; call_time: number | null; knock_in: boolean; worst_final: number | null
              redemption?: number | null; final_basket?: number | null; is_loss?: boolean }
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
  cover_logo_base64?: string      // white knockout logo for the cover
  cover_sigil_base64?: string     // emblem/sigil shown on the cover (≠ wordmark)
  cover_image_base64?: string     // full-bleed cover background photo
  back_image_base64?: string      // full-bleed photo for the disclaimer back page
  filler_images_base64?: string[] // pool of report photos: cover/back fallback + void-filler bands cycle through it
  cover_metrics?: string[]        // which KEY TERMS show on the at-a-glance cover rail (order = render order)
  cover_overlay_color?: string    // overlay colour over the cover/back photo
  cover_overlay_opacity?: string | number  // 0..1
  title_font?: string             // headings font (fonts/brand/<Name>-Bold.ttf)
  body_font?: string              // body font
  title_font_files?: Record<string, string>  // {Style: base64 TTF} embedded in the config
  body_font_files?: Record<string, string>
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
  compare_terms?: NoteTerms | null   // Note B — adds an A/B comparison section
  report_kind?: string | null        // audience preset key — stamped on the cover
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

export interface CoverPhoto {
  id: number
  thumb: string
  src: string
  photographer: string | null
  alt: string
  term?: string
}
