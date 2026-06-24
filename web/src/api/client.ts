import type {
  BacktestResult, ConfigMeta, ExplorerData, Health, LiveResult, LogoData, NoteTerms,
  ReportRequest, SimResult, SimulateRequest, UnderlyingMetric, UnderlyingOption,
} from './types'

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json()
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    let detail = await r.text()
    try { detail = JSON.parse(detail).detail ?? detail } catch { /* keep text */ }
    throw new Error(detail)
  }
  return r.json()
}

export const api = {
  health: () => jget<Health>('/api/health'),
  underlyings: () => jget<UnderlyingOption[]>('/api/underlyings'),
  configs: () => jget<ConfigMeta[]>('/api/configs'),
  config: (file: string) => jget<NoteTerms>(`/api/configs/${file}`),
  logos: () => jget<LogoData>('/api/logos'),
  simulate: (req: SimulateRequest) => jpost<SimResult>('/api/simulate', req),
  backtest: (terms: NoteTerms, lang = 'en', history_years: number | null = null) =>
    jpost<BacktestResult>('/api/backtest', { terms, history_years, lang }),
  live: (terms: NoteTerms, lang = 'en') =>
    jpost<LiveResult>('/api/live', { terms, lang }),
  underlyingMetrics: (tickers: Record<string, string>, lang = 'en') =>
    jpost<UnderlyingMetric[]>('/api/underlyings/metrics', { tickers, lang }),
  report: async (body: ReportRequest): Promise<Response> => {
    const r = await fetch('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) {
      let detail = await r.text()
      try { detail = JSON.parse(detail).detail ?? detail } catch { /* keep text */ }
      throw new Error(detail)
    }
    return r
  },
  runPaths: (runId: string, sample = 400) =>
    jget<ExplorerData>(`/api/runs/${runId}/paths?sample=${sample}`),
  backtestPaths: (terms: NoteTerms, seed = 7, sample = 400) =>
    jpost<ExplorerData>(`/api/backtest/paths?sample=${sample}&seed=${seed}`, { terms }),
}
