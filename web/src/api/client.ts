import type {
  BacktestResult, BtRange, ConfigMeta, DescribeResult, ExplorerData, Health, InspectFilters,
  InspectResult, LiveResult, LogoData, NoteTerms, ReportRequest, SimResult, SimulateRequest,
  UnderlyingMetric, UnderlyingOption,
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
  parseConfig: (config: unknown) => jpost<NoteTerms>('/api/configs/parse', { config }),
  logos: () => jget<LogoData>('/api/logos'),
  simulate: (req: SimulateRequest) => jpost<SimResult>('/api/simulate', req),
  backtest: (terms: NoteTerms, lang = 'en', range?: BtRange) =>
    jpost<BacktestResult>('/api/backtest', { terms, lang, bt_start: range?.start ?? null, bt_end: range?.end ?? null }),
  live: (terms: NoteTerms, lang = 'en') =>
    jpost<LiveResult>('/api/live', { terms, lang }),
  underlyingMetrics: (tickers: Record<string, string>, lang = 'en') =>
    jpost<UnderlyingMetric[]>('/api/underlyings/metrics', { tickers, lang }),
  quotes: (symbols: string[]) =>
    jpost<Record<string, { price: number | null; change: number | null }>>('/api/quotes', { symbols }),
  describe: (issuer: string | null, symbols: string[], lang = 'en') =>
    jpost<DescribeResult>('/api/describe', { issuer, symbols, lang }),
  brandingList: () => jget<{ file: string; firm_name: string }[]>('/api/branding'),
  branding: (file: string) => jget<Record<string, unknown>>(`/api/branding/${file}`),
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
  backtestPaths: (terms: NoteTerms, seed = 7, sample = 400, range?: BtRange) =>
    jpost<ExplorerData>(`/api/backtest/paths?sample=${sample}&seed=${seed}`, { terms, bt_start: range?.start ?? null, bt_end: range?.end ?? null }),
  inspectRun: (runId: string, body: { filters?: InspectFilters; position?: number; randomize?: boolean; title?: string | null; lang?: string }) =>
    jpost<InspectResult>(`/api/runs/${runId}/inspect`, body),
  backtestInspect: (terms: NoteTerms, body: { filters?: InspectFilters; position?: number; randomize?: boolean; lang?: string }, range?: BtRange) =>
    jpost<InspectResult>('/api/backtest/inspect', { terms, ...body, bt_start: range?.start ?? null, bt_end: range?.end ?? null }),
}
