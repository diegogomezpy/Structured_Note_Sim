import type {
  BacktestResult, BtRange, CompareResult, ConfigMeta, CoverPhoto, DescribeResult, ExplorerData, Health, HistorySpan,
  InspectFilters, InspectResult, LiveResult, LogoData, NoteTerms, Quote, ReportRequest, SimResult, SimulateRequest,
  UnderlyingMetric, UnderlyingOption,
} from './types'

/** Typed API failure. The backend returns a uniform {ok:false, error:{status,
    message}} body (older builds returned {detail}); both are unwrapped here. */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function throwApiError(r: Response): Promise<never> {
  let message = `${r.status} ${r.statusText}`.trim()
  try {
    const j = JSON.parse(await r.text())
    message = j?.error?.message ?? j?.detail ?? message
  } catch { /* non-JSON error body — keep the status line */ }
  throw new ApiError(r.status, message)
}

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) return throwApiError(r)
  return r.json()
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) return throwApiError(r)
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
  compare: (terms_a: NoteTerms, terms_b: NoteTerms,
            opts?: { n_paths?: number; seed?: number; calib_years?: number; engine?: string; lang?: string }) =>
    jpost<CompareResult>('/api/compare', { terms_a, terms_b, ...opts }),
  backtest: (terms: NoteTerms, lang = 'en', range?: BtRange) =>
    jpost<BacktestResult>('/api/backtest', { terms, lang, bt_start: range?.start ?? null, bt_end: range?.end ?? null }),
  live: (terms: NoteTerms, lang = 'en') =>
    jpost<LiveResult>('/api/live', { terms, lang }),
  underlyingMetrics: (tickers: Record<string, string>, lang = 'en') =>
    jpost<UnderlyingMetric[]>('/api/underlyings/metrics', { tickers, lang }),
  history: (tickers: Record<string, string>) =>
    jpost<HistorySpan>('/api/history', { tickers }),
  quotes: (symbols: string[]) =>
    jpost<Record<string, Quote>>('/api/quotes', { symbols }),
  describe: (issuer: string | null, symbols: string[], lang = 'en') =>
    jpost<DescribeResult>('/api/describe', { issuer, symbols, lang }),
  /** Fonts the PDF can actually render — the Designer offers exactly these and
      the preview @font-faces the same files, so a pick looks identical in both. */
  fonts: () => jget<{ family: string; file: string; styles: string[]; builtin: boolean }[]>('/api/fonts'),
  brandingList: () => jget<{ file: string; firm_name: string }[]>('/api/branding'),
  branding: (file: string) => jget<Record<string, unknown>>(`/api/branding/${file}`),
  coverSectors: () => jget<{ available: boolean; sectors: string[] }>('/api/cover/sectors'),
  coverPhotos: (sector: string, opts?: { n?: number; exclude?: (number | string)[] }) => {
    const q = new URLSearchParams({ sector })
    if (opts?.n) q.set('n', String(opts.n))
    if (opts?.exclude?.length) q.set('exclude', opts.exclude.join(','))
    return jget<{ available: boolean; sector: string; photos: CoverPhoto[] }>(`/api/cover/photos?${q.toString()}`)
  },
  coverPhotoProxy: (u: string) => `/api/cover/photo?u=${encodeURIComponent(u)}`,
  report: async (body: ReportRequest): Promise<Response> => {
    const r = await fetch('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) return throwApiError(r)
    return r
  },
  // Async report: start a background render, poll status, download the result —
  // so a 5-40s PDF build never blocks the API worker.
  reportStart: (body: ReportRequest) => jpost<{ job_id: string }>('/api/report/start', body),
  reportStatus: (jobId: string) =>
    jget<{ status: 'pending' | 'done' | 'error'; error?: string | null }>(`/api/report/status/${jobId}`),
  reportResult: async (jobId: string): Promise<Response> => {
    const r = await fetch(`/api/report/result/${jobId}`)
    if (!r.ok) return throwApiError(r)
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
