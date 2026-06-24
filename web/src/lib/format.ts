/* Display formatting. Every number that reaches the screen goes through one of
   these so we never leak float artifacts and percentages stay consistent. */

export function pct(x: number | null | undefined, dp = 1): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return `${(x * 100).toFixed(dp)}%`
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
