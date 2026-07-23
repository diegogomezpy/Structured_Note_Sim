/* Derived term-sheet values, mirroring the @property logic in core/note.py so
   the timeline can render before any simulation. Derived values are never
   stored — recomputed from the human-readable fields, same as the backend. */
import type { NoteTerms } from '../api/types'
import { pct } from './format'

const FREQ_TO_PERIODS: Record<string, number> = {
  monthly: 12, quarterly: 4, 'semi-annual': 2, annual: 1,
}

export function periodsPerYear(t: NoteTerms): number {
  return FREQ_TO_PERIODS[t.payment_freq] ?? 4
}

/* Maturity is STORED in years — that's the term-sheet JSON contract and what the
   quant core computes on, so neither changes. The UI quotes and edits it in
   months (how tenors are actually spoken), converting only at the boundary. */
export const monthsOf = (years: number) => Math.round(years * 12)
export const yearsOfMonths = (months: number) => months / 12
/** Years → months, unrounded — for durations quoted with decimals (avg time to
    autocall, elapsed/remaining, chart time axes). */
export const monthsNum = (years: number) => years * 12
/** Maturity for display, e.g. "36M". */
export const maturityLabel = (years: number) => `${monthsOf(years)}M`

export function nObs(t: NoteTerms): number {
  return Math.max(1, Math.round(t.maturity * periodsPerYear(t)))
}

export function couponRate(t: NoteTerms): number {
  return t.coupon_pa / periodsPerYear(t)
}

/** Observation times as fractions of maturity, t_k = k/nObs for k=1..nObs. */
export function obsFractions(t: NoteTerms): number[] {
  const n = nObs(t)
  return Array.from({ length: n }, (_, i) => (i + 1) / n)
}

export function tickerList(t: NoteTerms): string[] {
  return Object.values(t.tickers ?? {})
}

/** Per-observation autocall barrier levels (mirrors core.note.autocall_barrier_schedule).
    Constant at autocall_barrier unless autocall_step_down > 0, in which case it
    declines each period from autocall_start_period, floored at autocall_floor. */
export function autocallSchedule(t: NoteTerms): number[] {
  const n = nObs(t)
  const levels = Array.from({ length: n }, () => t.autocall_barrier)
  const step = t.autocall_step_down ?? 0
  if (step > 0) {
    for (let j = t.autocall_start_period; j <= n; j++) {
      let lvl = t.autocall_barrier - step * (j - t.autocall_start_period)
      if (t.autocall_floor != null) lvl = Math.max(lvl, t.autocall_floor)
      levels[j - 1] = lvl
    }
  }
  return levels
}

/** True when the autocall barrier steps down over the schedule. */
export function hasStepDown(t: NoteTerms): boolean {
  return (t.autocall_step_down ?? 0) > 0
}

/** One-line summary of a Participation note's payoff — its downside × upside
    profile, not the (irrelevant) coupon/autocall ladder. E.g.
    "Full protection · Linear 100% · upside cap 160%" or, for a cliquet,
    "Cliquet · Quarterly · Full protection · Linear 100% · upside cap 108%". */
export function participationSummary(terms: NoteTerms, tr: (k: string) => string): string {
  const dn = terms.participation_downside ?? 'full'
  const up = terms.participation_upside ?? 'linear'
  const prot = terms.protection_level ?? 1
  const rate = terms.participation_rate ?? 1
  const strike = terms.participation_strike ?? 1
  const capVal = terms.participation_periodic ? (terms.period_cap ?? null) : (terms.upside_cap ?? null)
  const segs: string[] = []
  if (terms.participation_periodic) segs.push(`${tr('grp_cliquet')} · ${tr(`freq_${terms.payment_freq}`)}`)
  // Downside style (+ its protection level; `full` at par shows no number).
  if (dn === 'bear') segs.push(`${tr('pd_bear')} ${pct(rate, 0)}`)
  else if (dn === 'full') segs.push(prot < 0.999 ? `${tr('pd_full')} ${pct(prot, 0)}` : tr('pd_full'))
  else segs.push(`${tr(`pd_${dn}`)} ${pct(prot, 0)}`)
  // Upside style (a `bear` note defines its own payoff — no separate upside).
  if (dn !== 'bear') {
    if (up === 'digital') segs.push(`${tr('pu_digital')} +${pct(terms.digital_payout ?? 0, 0)}`)
    else if (up === 'shark_fin') segs.push(terms.knockout_level != null ? `${tr('pu_shark_fin')} ${pct(terms.knockout_level, 0)}` : tr('pu_shark_fin'))
    else segs.push(`${tr('pu_linear')} ${pct(rate, 0)}${capVal != null ? ` · ${tr('upside_cap').toLowerCase()} ${pct(1 + capVal, 0)}` : ''}`)
  }
  if (Math.abs(strike - 1) > 1e-6) segs.push(`${tr('participation_strike').toLowerCase()} ${pct(strike, 0)}`)
  return segs.join(' · ')
}

/** Key/value rows for the note-features table — the web mirror of
    app/pdf_report.py:_term_rows, so the "at a glance" table on the page shows the
    same fields as the PDF's Note Terms table. Only fields the note actually uses
    add a row (step-down, floor, premium-at-call, issue date), same as the PDF. */
export function noteTermRows(t: NoteTerms, tr: (k: string) => string): [string, string][] {
  if (t.note_type === 'participation' || (t.capital_guarantee ?? 0) > 0) {
    const rows: [string, string][] = [
      [tr('maturity'), maturityLabel(t.maturity)],
      [tr('participation_profile'), participationSummary(t, tr)],
      [tr('protection_level'), pct(t.protection_level ?? 1, 1)],
    ]
    if (t.issue_date) rows.push([tr('issue_date'), t.issue_date])
    return rows
  }
  const cper = couponRate(t)
  const bask = (k: string) => tr(`basket_${k}`)
  const rows: [string, string][] = [
    [tr('maturity'), `${maturityLabel(t.maturity)} · ${nObs(t)} ${tr('obs_abbr')} · ${tr(`freq_${t.payment_freq}`)}`],
  ]
  // Coupon terms only mean anything on a note that pays one.
  if (t.coupon_pa > 0) {
    rows.push([tr('coupon_pa'), `${pct(t.coupon_pa, 2)} · ${pct(cper, 2)}/${tr('per_period')}`])
    rows.push([tr('coupon_barrier'), t.coupon_barrier > 0 ? pct(t.coupon_barrier, 1) : tr('nd_unconditional')])
    rows.push([tr('memory'), t.memory ? tr('yes') : tr('no')])
    rows.push([tr('coupon_basket'), bask(t.coupon_basket)])
  }
  rows.push([tr('autocall_barrier'), pct(t.autocall_barrier, 1)])
  rows.push([tr('autocall_start'), `P${t.autocall_start_period}`])
  if ((t.autocall_step_down ?? 0) > 0) {
    rows.push([tr('ac_step_down'), pct(t.autocall_step_down as number, 1)])
    if (t.autocall_floor != null) rows.push([tr('ac_floor'), pct(t.autocall_floor, 0)])
  }
  rows.push([tr('autocall_basket'), bask(t.autocall_basket)])
  rows.push([tr('knock_in_barrier'), pct(t.knock_in_barrier, 1)])
  if (t.principal_protection != null && Math.abs(t.principal_protection - 1) > 1e-9)
    rows.push([tr('principal_protection'), pct(t.principal_protection, 1)])
  // Optional features appear ONLY when the note actually uses them — a row
  // reading "One-Star · Off" is noise, not information.
  if (t.one_star_level != null) {
    rows.push([tr('one_star_level'), pct(t.one_star_level, 0)])
    if (t.one_star_coupon) rows.push([tr('one_star_coupon'), tr('yes')])
    if (t.one_star_autocall) rows.push([tr('one_star_autocall'), tr('yes')])
  }
  if (t.zenith) {
    const capTxt = t.upside_cap != null ? ` · ${tr('upside_cap').toLowerCase()} ${pct(t.upside_cap, 0)}` : ''
    rows.push([tr('zenith'), `${pct(t.participation_rate ?? 1, 0)}${capTxt}`])
  }
  if (t.coupon_at_autocall_only) rows.push([tr('premium_at_call'), tr('yes')])
  if (t.issue_date) rows.push([tr('issue_date'), t.issue_date])
  return rows
}

/** One-line plain-language summary of the coupon schedule, e.g.
    "4 × Quarterly · 10.0% coupon p.a. · +2.50%/period · memory coupons".
    Routes to `participationSummary` for Participation notes (payoff, not ladder).
    `tr` is the i18n lookup; only plain keys are used (no interpolation vars). */
export function noteSummary(terms: NoteTerms, tr: (k: string) => string): string {
  if (terms.note_type === 'participation' || (terms.capital_guarantee ?? 0) > 0) return participationSummary(terms, tr)
  const n = nObs(terms)
  const cper = couponRate(terms)
  const couponNote = cper > 0 ? ` · +${pct(cper, 2)}/${tr('per_period')}` : ''
  return `${n} × ${tr(`freq_${terms.payment_freq}`)} · ${pct(terms.coupon_pa, 1)} ${tr('coupon_pa').toLowerCase()}${couponNote}${terms.memory ? ` · ${tr('memory').toLowerCase()}` : ''}`
}
