import { api } from '../api/client'
import { fetchUnderlyingMetricsCached } from './metricsStore'
import type { NoteTerms } from '../api/types'

/* Batch report generation. Each note is rendered by the same proven per-note
   sync /api/report path (one request = full CPU on Cloud Run — deliberately NOT
   the async job flow, which starves under CPU throttling), then the resulting
   PDFs are zipped in the browser. No backend endpoint is added. */

// Report scope → the fine-grained section keys sent to /api/report. These mirror
// the ReportPanel's section tree; an empty list means "everything" (the backend
// treats sections=[] as the full report). Keys that don't apply to a given note
// (e.g. live_* without an issue date) are silently ignored server-side.
export type BatchScope = 'details' | 'details_mc' | 'full'

const DETAILS = ['cover', 'note_description', 'note_diagram', 'note_terms', 'obs_schedule', 'issuer_info', 'underlying_breakdown']
const MC = ['mc_metrics', 'mc_outcome', 'mc_autocall', 'mc_irr', 'mc_wof']

export const SCOPE_KEYS: Record<BatchScope, string[]> = {
  details: DETAILS,
  details_mc: [...DETAILS, ...MC],
  full: [],            // [] ⇒ full report (all available sections)
}

// How many library photos to pull for a note in "auto" mode. The report uses the
// first as the cover, the second as the back page and the rest as filler bands,
// so a heavier report wants a few more. Kept modest to bound the Pexels fetches.
const PHOTO_COUNT: Record<BatchScope, number> = { details: 4, details_mc: 6, full: 8 }

export type PhotoMode = 'auto' | 'none'

/** Resolve the dominant sector for a note's underlyings, exactly like the
    CoverPhotoPicker does (backend fine-grained `sector_key`, else coarse Yahoo
    sector), falling back to the generic "markets" library. */
async function dominantSector(terms: NoteTerms, lang: string): Promise<string> {
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

/** Fetch `n` random industry photos for a note and return them as base64 data
    URLs (the form the PDF branding pool wants). Best-effort: if the Pexels
    library is unconfigured or a fetch fails, returns however many succeeded
    (possibly none) so the report still renders — just without photos. */
export async function autoIndustryPhotos(terms: NoteTerms, lang: string, scope: BatchScope): Promise<string[]> {
  const n = PHOTO_COUNT[scope]
  let sector = 'markets'
  try { sector = await dominantSector(terms, lang) } catch { /* markets */ }
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
