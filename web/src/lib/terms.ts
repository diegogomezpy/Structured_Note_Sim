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

/** The issuer split: `issuer_id` is what the app uses to FIND the issuer's info
    and logo; `issuer` is the display name. Either falls back to the other so a
    note that fills only one field still works (and legacy configs, which have
    only `issuer`, keep behaving exactly as before). */
export const issuerLookup = (t: NoteTerms): string => (t.issuer_id?.trim() || t.issuer?.trim() || '')
export const issuerName = (t: NoteTerms): string => (t.issuer?.trim() || t.issuer_id?.trim() || '')

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

/** What the position cost per unit of nominal — clean price + accrued. Mirrors
    NoteTerms.cost_basis; 1 = subscribed at par. */
export function costBasis(t: NoteTerms): number {
  return (t.purchase_price ?? 1) + (t.accrued_at_purchase ?? 0)
}

/** True when the note is held as a secondary-market position rather than a
    subscription at issue. Mirrors NoteTerms.is_secondary. */
export function isSecondary(t: NoteTerms): boolean {
  return Math.abs(costBasis(t) - 1) > 1e-9 || !!t.settlement_date
}

/** Term rows describing the POSITION (not the note) — only present once the note
    was actually bought on the secondary market, so a plain subscription's table
    is unchanged. Shared by the autocall and participation row builders. */
function positionRows(t: NoteTerms, tr: (k: string) => string): [string, string][] {
  const rows: [string, string][] = []
  if (isSecondary(t)) {
    if (t.settlement_date) rows.push([tr('settlement_date'), t.settlement_date])
    rows.push([tr('purchase_price'), pct(t.purchase_price ?? 1, 3)])
    if ((t.accrued_at_purchase ?? 0) > 0) {
      rows.push([tr('accrued_at_purchase'), pct(t.accrued_at_purchase as number, 3)])
      rows.push([tr('cost_basis'), pct(costBasis(t), 3)])
    }
  }
  // Seasoning changes what the simulation covers, so it belongs on the term
  // sheet's face — it is why the modelled horizon isn't the full tenor.
  if (t.seasoned) rows.push([tr('seasoned'), tr('seasoned_row')])
  return rows
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
    rows.push(...positionRows(t, tr))
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
  rows.push(...positionRows(t, tr))
  return rows
}

/* ── term-sheet diff (A vs B) ─────────────────────────────────────────────── */

type DiffFmt = 'pct' | 'months' | 'period' | 'bool' | 'text' | 'key' | 'tickers'

/** Fields worth diffing, in term-sheet reading order, with how to render each.
    `key` formats route through i18n (baskets, frequencies, participation styles);
    everything absent from a note simply never differs and never shows. */
const DIFF_FIELDS: [string, string, DiffFmt][] = [
  ['note_type', 'sec_note_type', 'key'],
  ['tickers', 'underlyings', 'tickers'],
  ['maturity', 'maturity', 'months'],
  ['payment_freq', 'frequency', 'key'],
  ['coupon_pa', 'coupon_pa', 'pct'],
  ['coupon_barrier', 'coupon_barrier', 'pct'],
  ['memory', 'memory', 'bool'],
  ['coupon_basket', 'coupon_basket', 'key'],
  ['autocall_barrier', 'autocall_barrier', 'pct'],
  ['autocall_start_period', 'autocall_start', 'period'],
  ['autocall_basket', 'autocall_basket', 'key'],
  ['autocall_step_down', 'ac_step_down', 'pct'],
  ['autocall_floor', 'ac_floor', 'pct'],
  ['knock_in_barrier', 'knock_in_barrier', 'pct'],
  ['principal_protection', 'principal_protection', 'pct'],
  ['one_star_level', 'one_star_level', 'pct'],
  ['one_star_coupon', 'one_star_coupon', 'bool'],
  ['one_star_autocall', 'one_star_autocall', 'bool'],
  ['coupon_at_autocall_only', 'premium_at_call', 'bool'],
  ['zenith', 'zenith', 'bool'],
  ['upside_cap', 'upside_cap', 'pct'],
  ['participation_downside', 'part_downside', 'key'],
  ['participation_upside', 'part_upside', 'key'],
  ['participation_basket', 'part_basket', 'key'],
  ['protection_level', 'protection_level', 'pct'],
  ['participation_rate', 'participation_rate', 'pct'],
  ['participation_strike', 'participation_strike', 'pct'],
  ['knockout_level', 'knockout_level', 'pct'],
  ['knockout_payout', 'knockout_payout', 'pct'],
  ['digital_payout', 'digital_payout', 'pct'],
  ['participation_periodic', 'part_periodic', 'bool'],
  ['period_cap', 'period_cap', 'pct'],
  ['issue_date', 'issue_date', 'text'],
  ['settlement_date', 'settlement_date', 'text'],
  ['purchase_price', 'purchase_price', 'pct'],
  ['accrued_at_purchase', 'accrued_at_purchase', 'pct'],
  ['seasoned', 'seasoned', 'bool'],
]

/** i18n key for an enum value, so 'worst_of' renders as "Worst-of". */
const ENUM_KEY: Record<string, (v: string) => string> = {
  coupon_basket: (v) => `basket_${v}`,
  autocall_basket: (v) => `basket_${v}`,
  participation_basket: (v) => `basket_${v}`,
  payment_freq: (v) => `freq_${v}`,
  participation_downside: (v) => `pd_${v}`,
  participation_upside: (v) => `pu_${v}`,
  note_type: (v) => `nt_${v}`,
}

function fmtDiff(field: string, kind: DiffFmt, v: unknown, tr: (k: string) => string): string {
  if (v == null || v === '') return '—'
  switch (kind) {
    case 'pct': return typeof v === 'number' ? pct(v, 2) : String(v)
    case 'months': return typeof v === 'number' ? maturityLabel(v) : String(v)
    case 'period': return `P${v}`
    case 'bool': return v ? tr('yes') : tr('no')
    case 'tickers': return Object.values(v as Record<string, string>).join(', ')
    case 'key': return tr(ENUM_KEY[field]?.(String(v)) ?? String(v))
    default: return String(v)
  }
}

/** The fields that actually DIFFER between two notes, formatted for display.
    This is the question the two structure diagrams can't answer at a glance —
    "what did I change?" — and it is what makes every metric delta below it
    attributable. Falsy-vs-missing is normalised so `null` and `0` and `false`
    don't read as a change when neither note uses the feature. */
export function termDiffRows(a: NoteTerms, b: NoteTerms, tr: (k: string) => string):
    { label: string; a: string; b: string }[] {
  const norm = (v: unknown) => (v == null || v === '' || v === false || v === 0 ? null : v)
  // A basket is a SET: the same underlyings listed in a different order is the
  // same note, and the payoff agrees (worst-of / best-of / average all reduce
  // across assets). JSON.stringify preserves insertion order, so compare a
  // sorted key instead or a reordered map reads as a change that isn't one.
  const basketKey = (v: unknown) =>
    Object.entries((v ?? {}) as Record<string, string>)
      .map(([sym, name]) => `${sym}=${name}`).sort().join('|')
  const rows: { label: string; a: string; b: string }[] = []
  for (const [field, labelKey, kind] of DIFF_FIELDS) {
    const va = (a as Record<string, unknown>)[field]
    const vb = (b as Record<string, unknown>)[field]
    const same = kind === 'tickers'
      ? basketKey(va) === basketKey(vb)
      : JSON.stringify(norm(va)) === JSON.stringify(norm(vb))
    if (same) continue
    rows.push({ label: tr(labelKey), a: fmtDiff(field, kind, va, tr), b: fmtDiff(field, kind, vb, tr) })
  }
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
