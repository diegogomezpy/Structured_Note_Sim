/* Display formatting. Every number that reaches the screen goes through one of
   these so we never leak float artifacts and percentages stay consistent. */

export function pct(x: number | null | undefined, dp = 1): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return `${(x * 100).toFixed(dp)}%`
}

/** Percent with up to `dp` decimals but trailing zeros trimmed — 50% (not 50.0%),
    50.5%, 50.125%. Used for barrier levels, which can carry fine precision. */
export function pctTrim(x: number | null | undefined, dp = 3): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return `${parseFloat((x * 100).toFixed(dp))}%`
}

export function pctSigned(x: number | null | undefined, dp = 1): string {
  if (x == null || !Number.isFinite(x)) return '—'
  const v = x * 100
  return `${v >= 0 ? '+' : ''}${v.toFixed(dp)}%`
}

export function num(x: number | null | undefined, dp = 1): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return x.toFixed(dp)
}

/** Expected payout is quoted per 100 nominal — the engine returns a fraction. */
export function per100(x: number | null | undefined, dp = 1): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return (x * 100).toFixed(dp)
}

/** Compact currency market cap: —, $1.2T, $265.0B, $980.0M. */
export function marketCap(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  for (const [unit, div] of [['T', 1e12], ['B', 1e9], ['M', 1e6]] as const) {
    if (v >= div) return `$${(v / div).toFixed(1)}${unit}`
  }
  return `$${v.toLocaleString()}`
}

/** Price with thousands separators and 2dp. */
export function price(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
