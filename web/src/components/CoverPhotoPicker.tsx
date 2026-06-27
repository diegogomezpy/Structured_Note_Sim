import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { fetchUnderlyingMetricsCached } from '../lib/metricsStore'
import { Select } from './fields'
import Icon from './Icon'
import type { CoverPhoto, NoteTerms } from '../api/types'

// Remember the sector resolved for a given underlying set so re-opening a note
// we've seen before paints the grid immediately instead of waiting on the
// (network) metrics lookup again. Module-level → survives remounts this session.
const _sectorMemo = new Map<string, string>()

/** Industry report-photo picker — a built-in library (via Pexels) of professional
    photos keyed by sector. The sector is suggested from the note's underlyings
    (and overridable). This is a MULTI-select: every chosen photo is embedded into
    the branding's image pool (`filler_images_base64`), which drives the cover, the
    back page and the empty-space filler bands — each band cycles to the next photo
    so a report with several gaps shows variety instead of one repeated image.
    Hidden cleanly when no Pexels key is configured; manual upload still works. */
export default function CoverPhotoPicker({ terms, selected, onChange }: {
  terms: NoteTerms
  selected: string[]
  onChange: (urls: string[]) => void
}) {
  const { t, lang } = useI18n()
  const [available, setAvailable] = useState<boolean | null>(null)
  const [sectors, setSectors] = useState<string[]>([])
  const [sector, setSector] = useState('markets')
  const [photos, setPhotos] = useState<CoverPhoto[]>([])
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  // Maps a library photo's id → the data URL we fetched for it this session, so
  // we can show a check on already-picked tiles and toggle them back off.
  const [idToUrl, setIdToUrl] = useState<Record<number, string>>({})
  // True once the user manually picks a sector → stop auto-re-suggesting on note
  // changes so their choice sticks.
  const userPicked = useRef(false)
  // Latest shown photos, read inside the refresh handler without re-subscribing.
  const photosRef = useRef<CoverPhoto[]>([])
  photosRef.current = photos
  // Signature of the current underlyings; drives the re-suggest effect so the
  // grid tracks whichever note is loaded.
  const tickKey = useMemo(
    () => Object.keys(terms.tickers ?? {}).sort().join(','), [terms.tickers])

  useEffect(() => {
    api.coverSectors().then((r) => { setAvailable(r.available); setSectors(r.sectors) }).catch(() => setAvailable(false))
  }, [])

  // Fetch photos for a sector. `refresh` requests a fresh random sample and
  // holds back the ids already on screen / selected so the set actually changes.
  const load = async (sec: string, refresh = false) => {
    setLoading(true)
    try {
      const exclude = refresh
        ? [...photosRef.current.map((p) => p.id),
           ...Object.entries(idToUrl).filter(([, u]) => selected.includes(u)).map(([id]) => id)]
        : undefined
      const r = await api.coverPhotos(sec, refresh ? { exclude } : undefined)
      setSector(r.sector); setPhotos(r.photos)
    } catch { setPhotos([]) }
    finally { setLoading(false) }
  }

  // Suggest + load the sector from the underlyings' dominant Yahoo sector.
  // Re-runs whenever the loaded note's underlyings change (so the image section
  // tracks the note), unless the user has manually chosen a sector. Resolves
  // instantly from the per-note memo / cached metrics when possible.
  useEffect(() => {
    if (available !== true) return
    // First availability OR a freshly loaded note (tickKey changed) → resume
    // auto-suggestion; a manual sector pick only sticks for the current note.
    userPicked.current = false
    const memo = _sectorMemo.get(tickKey)
    if (memo) { load(memo); return }
    const tickers = terms.tickers ?? {}
    if (!Object.keys(tickers).length) { load('markets'); return }
    let cancelled = false
    fetchUnderlyingMetricsCached(tickers, lang).then((rows) => {
      if (cancelled || userPicked.current) return
      const counts: Record<string, number> = {}
      for (const r of rows) { const s = (r.sector || '').trim(); if (s) counts[s] = (counts[s] ?? 0) + 1 }
      const dom = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0]
      const sec = dom || 'markets'
      _sectorMemo.set(tickKey, sec)
      load(sec)
    }).catch(() => { if (!cancelled && !userPicked.current) load('markets') })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [available, tickKey])

  const isPicked = (p: CoverPhoto) => {
    const u = idToUrl[p.id]
    return !!u && selected.includes(u)
  }

  const toggle = async (p: CoverPhoto) => {
    // Already in the pool → remove it.
    const existing = idToUrl[p.id]
    if (existing && selected.includes(existing)) {
      onChange(selected.filter((u) => u !== existing))
      return
    }
    setBusyId(p.id)
    try {
      const resp = await fetch(api.coverPhotoProxy(p.src))
      if (!resp.ok) throw new Error('proxy failed')
      const blob = await resp.blob()
      const dataUrl = await new Promise<string>((res, rej) => {
        const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.onerror = rej; fr.readAsDataURL(blob)
      })
      setIdToUrl((m) => ({ ...m, [p.id]: dataUrl }))
      if (!selected.includes(dataUrl)) onChange([...selected, dataUrl])
    } catch { /* leave unchanged */ }
    finally { setBusyId(null) }
  }

  // The chosen-pool strip (incl. images loaded from a branding file) — shown
  // regardless of Pexels availability so the pool can always be reviewed/removed.
  // Order matters: 1st = cover, 2nd = back page, rest cycle into the filler bands.
  const selectedStrip = selected.length > 0 && (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 5 }}>
        {t('cover_lib_selected', { n: selected.length })}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
        {selected.map((u, i) => (
          <div key={i} style={{ position: 'relative', width: 78, aspectRatio: '16 / 10', borderRadius: 7, overflow: 'hidden', border: '1px solid var(--border)' }}>
            <img src={u} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            <span style={{ position: 'absolute', top: 2, left: 3, fontSize: 9.5, fontWeight: 700, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.7)' }}>
              {i === 0 ? t('cover_role_cover') : i === 1 ? t('cover_role_back') : `#${i + 1}`}
            </span>
            <button onClick={() => onChange(selected.filter((_, j) => j !== i))} aria-label={t('det_reset_logo')}
                    style={{ position: 'absolute', top: 2, right: 2, width: 16, height: 16, padding: 0, borderRadius: '50%', border: 'none', cursor: 'pointer', background: 'rgba(15,18,16,.65)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="x" size={10} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )

  if (available === null) return selectedStrip ? <div style={{ marginTop: 4 }}>{selectedStrip}</div> : null
  if (available === false) {
    return (
      <div style={{ marginTop: 4 }}>
        {selectedStrip}
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.5 }}>{t('cover_lib_unconfigured')}</div>
      </div>
    )
  }

  return (
    <div style={{ marginTop: 4 }}>
      {selectedStrip}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 9 }}>
        <div style={{ minWidth: 190 }}>
          <Select value={sector} onChange={(s) => { userPicked.current = true; load(s) }}
                  ariaLabel={t('cover_lib_sector')}
                  options={sectors.map((s) => ({ value: s, label: t(`sector_${s}`) }))} />
        </div>
        <button onClick={() => load(sector, true)} disabled={loading} title={t('cover_lib_refresh')}
                aria-label={t('cover_lib_refresh')} className="lift"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 11px',
                  borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface-2)',
                  color: 'var(--text)', cursor: loading ? 'default' : 'pointer', fontSize: 12,
                  opacity: loading ? 0.6 : 1,
                }}>
          <Icon name={loading ? 'spinner' : 'refresh'} size={14} />
          {t('cover_lib_refresh')}
        </button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(112px, 1fr))', gap: 8 }}>
        {photos.map((p) => (
          <button key={p.id} onClick={() => toggle(p)} title={p.alt} className="lift"
                  style={{
                    position: 'relative', padding: 0, cursor: 'pointer', overflow: 'hidden',
                    borderRadius: 9, aspectRatio: '16 / 10', background: 'var(--surface-2)',
                    border: isPicked(p) ? '2px solid var(--accent)' : '1px solid var(--border)',
                  }}>
            <img src={p.thumb} alt={p.alt} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            {busyId === p.id && (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(15,18,16,.45)', color: '#fff' }}>
                <Icon name="spinner" size={18} />
              </div>
            )}
            {isPicked(p) && busyId !== p.id && (
              <div style={{ position: 'absolute', top: 4, right: 4, width: 18, height: 18, borderRadius: '50%', background: 'var(--accent)', color: '#fffefb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icon name="check" size={12} />
              </div>
            )}
          </button>
        ))}
      </div>
      {!loading && !photos.length && <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 4 }}>{t('cover_lib_empty')}</div>}
    </div>
  )
}
