import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { fetchUnderlyingMetricsCached } from '../lib/metricsStore'
import { useLocalImages } from '../lib/localFolder'
import { Select } from './fields'
import FolderConnect from './FolderConnect'
import Icon from './Icon'
import type { CoverPhoto, NoteTerms } from '../api/types'

// Remember the sector resolved for a given underlying set so re-opening a note
// we've seen before paints the grid immediately instead of waiting on the
// (network) metrics lookup again. Module-level → survives remounts this session.
const _sectorMemo = new Map<string, string>()

/** Industry report-photo picker — a built-in library (via Pexels) of professional
    photos keyed by sector, PLUS your own uploads / a connected image folder. This
    is a MULTI-select: the chosen pool (`filler_images_base64`) drives the cover
    (1st), the back page (2nd) and the empty-space filler bands (the rest, in
    order). The selected strip is drag-reorderable and capped to `max` — how many
    photos the current report can actually show. */
export default function CoverPhotoPicker({ terms, selected, onChange, max }: {
  terms: NoteTerms
  selected: string[]
  onChange: (urls: string[]) => void
  max?: number
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
  // Rolling history of recently shown photo ids → held back on refresh so the
  // grid keeps cycling through the pool instead of repeating the same shots.
  const seenRef = useRef<number[]>([])
  const SHOWN = 16        // photos per (re)load
  const SEEN_CAP = 40     // how many recent ids to remember
  // Drag-to-reorder state for the selected strip.
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  // A connected local folder of images, auto-detected and offered as photos.
  const imgFolder = useLocalImages('report-images')

  const atCap = max != null && selected.length >= max
  const addUrl = (u: string) => {
    if (!selected.includes(u) && (max == null || selected.length < max)) onChange([...selected, u])
  }
  const toggleUrl = (u: string) => (selected.includes(u) ? onChange(selected.filter((x) => x !== u)) : addUrl(u))
  const reorder = (from: number, to: number) => {
    if (from === to || from < 0 || to < 0) return
    const next = [...selected]; const [m] = next.splice(from, 1); next.splice(to, 0, m); onChange(next)
  }

  // Signature of the current underlyings; drives the re-suggest effect.
  const tickKey = useMemo(
    () => Object.keys(terms.tickers ?? {}).sort().join(','), [terms.tickers])

  useEffect(() => {
    api.coverSectors().then((r) => { setAvailable(r.available); setSectors(r.sectors) }).catch(() => setAvailable(false))
  }, [])

  // Fetch photos for a sector. `refresh` requests a fresh random sample and
  // holds back recently shown / selected ids so the set actually changes.
  const load = async (sec: string, refresh = false) => {
    setLoading(true)
    try {
      const selIds = Object.entries(idToUrl)
        .filter(([, u]) => selected.includes(u)).map(([id]) => Number(id))
      const exclude = refresh
        ? Array.from(new Set([...seenRef.current, ...selIds]))
        : undefined
      const r = await api.coverPhotos(sec, { n: SHOWN, exclude })
      setSector(r.sector); setPhotos(r.photos)
      const ids = r.photos.map((p) => p.id)
      seenRef.current = refresh ? [...seenRef.current, ...ids].slice(-SEEN_CAP) : ids
    } catch { setPhotos([]) }
    finally { setLoading(false) }
  }

  // Suggest + load the sector from the underlyings' dominant Yahoo sector.
  // Re-runs whenever the loaded note's underlyings change (so the image section
  // tracks the note), unless the user has manually chosen a sector.
  useEffect(() => {
    if (available !== true) return
    userPicked.current = false
    const memo = _sectorMemo.get(tickKey)
    if (memo) { load(memo); return }
    const tickers = terms.tickers ?? {}
    if (!Object.keys(tickers).length) { load('markets'); return }
    let cancelled = false
    fetchUnderlyingMetricsCached(tickers, lang).then((rows) => {
      if (cancelled || userPicked.current) return
      const counts: Record<string, number> = {}
      // Prefer the backend-resolved fine-grained key (industry-first, so a
      // defense / semiconductor / luxury / bank name reaches its own sector),
      // falling back to the coarse Yahoo sector for older responses.
      for (const r of rows) { const s = (r.sector_key || r.sector || '').trim(); if (s) counts[s] = (counts[s] ?? 0) + 1 }
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
    const existing = idToUrl[p.id]
    if (existing && selected.includes(existing)) { onChange(selected.filter((u) => u !== existing)); return }
    if (atCap) return                       // at capacity — can't add more
    setBusyId(p.id)
    try {
      const resp = await fetch(api.coverPhotoProxy(p.src))
      if (!resp.ok) throw new Error('proxy failed')
      const blob = await resp.blob()
      const dataUrl = await new Promise<string>((res, rej) => {
        const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.onerror = rej; fr.readAsDataURL(blob)
      })
      setIdToUrl((m) => ({ ...m, [p.id]: dataUrl }))
      addUrl(dataUrl)
    } catch { /* leave unchanged */ }
    finally { setBusyId(null) }
  }

  // Small drop-target wrapper for the strip tiles → drag to reorder.
  const dragProps = (i: number) => ({
    draggable: true,
    onDragStart: () => setDragIdx(i),
    onDragOver: (e: React.DragEvent) => { e.preventDefault() },
    onDrop: (e: React.DragEvent) => { e.preventDefault(); if (dragIdx != null) reorder(dragIdx, i); setDragIdx(null) },
    onDragEnd: () => setDragIdx(null),
  })

  // The chosen-pool strip — shown regardless of Pexels availability so the pool
  // can always be reviewed, reordered and removed. Order matters: 1st = cover,
  // 2nd = back page, the rest cycle into the filler bands (drag to change).
  const selectedStrip = selected.length > 0 && (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 5, display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <span>{max != null ? t('cover_lib_selected_max', { n: selected.length, max }) : t('cover_lib_selected', { n: selected.length })}</span>
        {selected.length > 1 && <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{t('cover_lib_reorder')}</span>}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
        {selected.map((u, i) => (
          <div key={i} {...dragProps(i)}
               style={{ position: 'relative', width: 78, aspectRatio: '16 / 10', borderRadius: 7, overflow: 'hidden',
                        border: dragIdx === i ? '1px dashed var(--accent)' : '1px solid var(--border)',
                        cursor: 'grab', opacity: dragIdx === i ? 0.4 : 1 }}>
            <img src={u} alt="" draggable={false} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
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

  // Connected image-folder section (works with or without Pexels). Each detected
  // image is a tile that toggles into the pool.
  const folderSection = imgFolder.supported && (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('cover_folder')}</div>
      <div style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.5 }}>{t('cover_folder_hint')}</div>
      <FolderConnect fld={imgFolder} />
      {imgFolder.files.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))', gap: 8, marginTop: 9 }}>
          {imgFolder.files.map((f) => {
            const on = selected.includes(f.dataUrl)
            const disabled = atCap && !on
            return (
              <button key={f.name + f.dataUrl.slice(-12)} onClick={() => toggleUrl(f.dataUrl)} title={f.name}
                      disabled={disabled} className="lift"
                      style={{ position: 'relative', padding: 0, cursor: disabled ? 'not-allowed' : 'pointer', overflow: 'hidden',
                               borderRadius: 9, aspectRatio: '16 / 10', background: 'var(--surface-2)', opacity: disabled ? 0.45 : 1,
                               border: on ? '2px solid var(--accent)' : '1px solid var(--border)' }}>
                <img src={f.dataUrl} alt={f.name} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                {on && (
                  <div style={{ position: 'absolute', top: 4, right: 4, width: 18, height: 18, borderRadius: '50%', background: 'var(--accent)', color: '#fffefb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Icon name="check" size={12} />
                  </div>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )

  if (available === null) {
    return (selectedStrip || folderSection)
      ? <div style={{ marginTop: 4 }}>{selectedStrip}{folderSection}</div> : null
  }
  if (available === false) {
    return (
      <div style={{ marginTop: 4 }}>
        {selectedStrip}
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.5 }}>{t('cover_lib_unconfigured')}</div>
        {folderSection}
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
      {atCap && <div style={{ fontSize: 11, color: 'var(--amber)', marginBottom: 7 }}>{t('cover_lib_at_cap', { max: max ?? 0 })}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(112px, 1fr))', gap: 8 }}>
        {photos.map((p) => {
          const picked = isPicked(p)
          const disabled = atCap && !picked
          return (
            <button key={p.id} onClick={() => toggle(p)} title={p.alt} className="lift" disabled={disabled && busyId !== p.id}
                    style={{
                      position: 'relative', padding: 0, cursor: disabled ? 'not-allowed' : 'pointer', overflow: 'hidden',
                      borderRadius: 9, aspectRatio: '16 / 10', background: 'var(--surface-2)', opacity: disabled ? 0.45 : 1,
                      border: picked ? '2px solid var(--accent)' : '1px solid var(--border)',
                    }}>
              <img src={p.thumb} alt={p.alt} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
              {busyId === p.id && (
                <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(15,18,16,.45)', color: '#fff' }}>
                  <Icon name="spinner" size={18} />
                </div>
              )}
              {picked && busyId !== p.id && (
                <div style={{ position: 'absolute', top: 4, right: 4, width: 18, height: 18, borderRadius: '50%', background: 'var(--accent)', color: '#fffefb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon name="check" size={12} />
                </div>
              )}
            </button>
          )
        })}
      </div>
      {!loading && !photos.length && <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 4 }}>{t('cover_lib_empty')}</div>}
      {folderSection}
    </div>
  )
}
