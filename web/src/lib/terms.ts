/* Derived term-sheet values, mirroring the @property logic in core/note.py so
   the timeline can render before any simulation. Derived values are never
   stored — recomputed from the human-readable fields, same as the backend. */
import type { NoteTerms } from '../api/types'

const FREQ_TO_PERIODS: Record<string, number> = {
  monthly: 12, quarterly: 4, 'semi-annual': 2, annual: 1,
}

export function periodsPerYear(t: NoteTerms): number {
  return FREQ_TO_PERIODS[t.payment_freq] ?? 4
}

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
