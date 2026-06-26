import { api } from '../api/client'
import type { UnderlyingMetric } from '../api/types'

/** Promise cache for the (heavy) underlying-metrics endpoint, keyed on the
    symbol set + language. Lets the ticker tape reuse a result without firing a
    second 1Y price pull. Cleared on failure so a transient error can retry. */
const cache = new Map<string, Promise<UnderlyingMetric[]>>()

export function fetchUnderlyingMetricsCached(
  tickers: Record<string, string>, lang: string,
): Promise<UnderlyingMetric[]> {
  const key = Object.keys(tickers).sort().join(',') + '|' + lang
  let p = cache.get(key)
  if (!p) {
    p = api.underlyingMetrics(tickers, lang).catch((e) => { cache.delete(key); throw e })
    cache.set(key, p)
  }
  return p
}
