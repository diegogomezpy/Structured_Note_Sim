import type {
  ConfigMeta, Health, LogoData, NoteTerms, SimResult, SimulateRequest, UnderlyingOption,
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
}
