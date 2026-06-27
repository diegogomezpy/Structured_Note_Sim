import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { fetchUnderlyingMetricsCached } from '../lib/metricsStore'
import { Select } from './fields'
import Icon from './Icon'
import type { CoverPhoto, NoteTerms } from '../api/types'

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
  const suggested = useRef(false)

  useEffect(() => {
    api.coverSectors().then((r) => { setAvailable(r.available); setSectors(r.sectors) }).catch(() => setAvailable(false))
  }, [])

  const load = async (sec: string) => {
    setLoading(true)
    try { const r = await api.coverPhotos(sec); setSector(r.sector); setPhotos(r.photos) }
    catch { setPhotos([]) }
    finally { setLoading(false) }
  }

  // Suggest the sector once from the underlyings' dominant Yahoo sector.
  useEffect(() => {
    if (suggested.current || available !== true) return
    const tickers = terms.tickers ?? {}
    if (!Object.keys(tickers).length) { load('markets'); suggested.current = true; return }
    fetchUnderlyingMetricsCached(tickers, lang).then((rows) => {
      if (suggested.current) return
      const counts: Record<string, number> = {}
      for (const r of rows) { const s = (r.sector || '').trim(); if (s) counts[s] = (counts[s] ?? 0) + 1 }
      const dom = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0]
      suggested.current = true
      load(dom || 'markets')
    }).catch(() => { suggested.current = true; load('markets') })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [available])

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
          <Select value={sector} onChange={load} ariaLabel={t('cover_lib_sector')}
                  options={sectors.map((s) => ({ value: s, label: t(`sector_${s}`) }))} />
        </div>
        {loading && <Icon name="spinner" size={15} />}
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
