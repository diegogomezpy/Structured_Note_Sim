import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { fetchUnderlyingMetricsCached } from '../lib/metricsStore'
import { Select } from './fields'
import Icon from './Icon'
import type { CoverPhoto, NoteTerms } from '../api/types'

/** Industry cover-photo picker — a built-in library (via Pexels) of professional
    cover backgrounds keyed by sector. The sector is suggested from the note's
    underlyings (and overridable); picking a photo embeds it as the cover image so
    the branding config stays self-contained. Hidden cleanly when no Pexels key is
    configured on the backend; manual upload still works. */
export default function CoverPhotoPicker({ terms, onPick }: {
  terms: NoteTerms
  onPick: (dataUrl: string) => void
}) {
  const { t, lang } = useI18n()
  const [available, setAvailable] = useState<boolean | null>(null)
  const [sectors, setSectors] = useState<string[]>([])
  const [sector, setSector] = useState('markets')
  const [photos, setPhotos] = useState<CoverPhoto[]>([])
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [pickedId, setPickedId] = useState<number | null>(null)
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

  const pick = async (p: CoverPhoto) => {
    setBusyId(p.id)
    try {
      const resp = await fetch(api.coverPhotoProxy(p.src))
      if (!resp.ok) throw new Error('proxy failed')
      const blob = await resp.blob()
      const dataUrl = await new Promise<string>((res, rej) => {
        const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.onerror = rej; fr.readAsDataURL(blob)
      })
      onPick(dataUrl)
      setPickedId(p.id)
    } catch { /* leave unchanged */ }
    finally { setBusyId(null) }
  }

  if (available === null) return null
  if (available === false) {
    return <div style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.5, marginTop: 4 }}>{t('cover_lib_unconfigured')}</div>
  }

  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 9 }}>
        <div style={{ minWidth: 190 }}>
          <Select value={sector} onChange={load} ariaLabel={t('cover_lib_sector')}
                  options={sectors.map((s) => ({ value: s, label: t(`sector_${s}`) }))} />
        </div>
        {loading && <Icon name="spinner" size={15} />}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(112px, 1fr))', gap: 8 }}>
        {photos.map((p) => (
          <button key={p.id} onClick={() => pick(p)} title={p.alt} className="lift"
                  style={{
                    position: 'relative', padding: 0, cursor: 'pointer', overflow: 'hidden',
                    borderRadius: 9, aspectRatio: '16 / 10', background: 'var(--surface-2)',
                    border: pickedId === p.id ? '2px solid var(--accent)' : '1px solid var(--border)',
                  }}>
            <img src={p.thumb} alt={p.alt} loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            {busyId === p.id && (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(15,18,16,.45)', color: '#fff' }}>
                <Icon name="spinner" size={18} />
              </div>
            )}
            {pickedId === p.id && busyId !== p.id && (
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
