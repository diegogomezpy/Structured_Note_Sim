import { api } from '../api/client'
import { fetchUnderlyingMetricsCached } from './metricsStore'
import type { NoteTerms } from '../api/types'

/* Batch report generation helpers. Each note is rendered by the same proven
   per-note sync /api/report path (one request = full CPU on Cloud Run —
   deliberately NOT the async job flow, which starves under CPU throttling); the
   resulting PDFs are zipped in the browser. No backend endpoint is added. */

export type PhotoMode = 'auto' | 'custom' | 'none'

/** Resolve the dominant sector key for a note's underlyings, exactly like the
    CoverPhotoPicker (backend fine-grained `sector_key`, else coarse Yahoo
    sector), falling back to the generic "markets" library. Used both to fetch
    auto photos and to show the matched sector in the UI. */
export async function resolveSector(terms: NoteTerms, lang: string): Promise<string> {
  const tickers = terms.tickers ?? {}
  if (!Object.keys(tickers).length) return 'markets'
  try {
    const rows = await fetchUnderlyingMetricsCached(tickers, lang)
    const counts: Record<string, number> = {}
    for (const r of rows) {
      const s = (r.sector_key || r.sector || '').trim()
      if (s) counts[s] = (counts[s] ?? 0) + 1
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'markets'
  } catch { return 'markets' }
}

/** Fetch `n` sector-matched photos for a note as base64 data URLs (the form the
    PDF branding pool wants). Best-effort: if Pexels is unconfigured or a fetch
    fails, returns however many succeeded (possibly none) so the report still
    renders — just without those images. */
export async function autoIndustryPhotos(terms: NoteTerms, lang: string, n: number): Promise<string[]> {
  const sector = await resolveSector(terms, lang).catch(() => 'markets')
  let photos
  try {
    const r = await api.coverPhotos(sector, { n })
    if (!r.available) return []
    photos = r.photos
  } catch { return [] }
  const urls: string[] = []
  for (const p of photos) {
    try {
      const resp = await fetch(api.coverPhotoProxy(p.src))
      if (!resp.ok) continue
      const blob = await resp.blob()
      const dataUrl = await new Promise<string>((res, rej) => {
        const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.onerror = rej; fr.readAsDataURL(blob)
      })
      urls.push(dataUrl)
    } catch { /* skip this photo */ }
  }
  return urls
}

/** Photos a report can show: cover (1st) + back (2nd) + ~one filler per couple
    of sections. Mirrors the single-report cap, clamped to [4, 12]. */
export function photoCapacity(nSections: number): number {
  return Math.max(4, Math.min(12, 2 + Math.ceil(nSections / 2)))
}
