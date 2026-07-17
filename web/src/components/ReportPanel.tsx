import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { useToast } from './Toast'
import Panel from './Panel'
import Icon from './Icon'
import { Select } from './fields'
import FolderConnect from './FolderConnect'
import CoverPhotoPicker from './CoverPhotoPicker'
import { useTour, reportTour } from './Tour'
import { useLocalFolder } from '../lib/localFolder'
import type { Branding, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'
import { TREE, PRESET_ORDER, presetKeys, savePresetOverride, resetPresetOverride,
         isPresetCustomised, type Preset, type Group } from '../lib/reportSections'

type Status = 'idle' | 'running' | 'done' | 'error'

const CUSTOM_LS = 'mercator_report_custom'
const loadCustom = (): string[] | null => {
  try { const r = localStorage.getItem(CUSTOM_LS); return r ? (JSON.parse(r) as string[]) : null } catch { return null }
}

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get('Content-Disposition') || ''
  const m = cd.match(/filename="?([^"]+)"?/)
  return m ? m[1] : fallback
}

/** Normalize an image value for an <img> src. A loaded branding config may store
    the image as raw base64 WITHOUT the `data:` URL prefix (the PDF backend
    tolerates that; the browser doesn't, hence the broken-image previews). Sniff
    the format from the leading base64 bytes so the preview renders. */
function dataUrl(v?: string): string | undefined {
  if (!v) return undefined
  if (v.startsWith('data:') || v.startsWith('http') || v.startsWith('/')) return v
  let mime = 'image/png'
  if (v.startsWith('/9j/')) mime = 'image/jpeg'
  else if (v.startsWith('R0lGOD')) mime = 'image/gif'
  else if (v.startsWith('UklGR')) mime = 'image/webp'
  else if (v.startsWith('iVBOR')) mime = 'image/png'
  else if (v.includes('ftyp') || v.startsWith('AAAA')) mime = 'image/avif'
  return `data:${mime};base64,${v}`
}

/** Image preview that normalizes the src and, if the image still fails to load,
    simply renders nothing instead of a broken-image icon. */
function ImgPreview({ src, style }: { src?: string; style?: React.CSSProperties }) {
  const [ok, setOk] = useState(true)
  const url = dataUrl(src)
  useEffect(() => { setOk(true) }, [url])
  if (!url || !ok) return null
  return <img src={url} alt="" onError={() => setOk(false)} style={style} />
}

function Check({ on, indeterminate }: { on: boolean; indeterminate?: boolean }) {
  return (
    <span style={{
      width: 18, height: 18, borderRadius: 6, flexShrink: 0,
      border: `1.5px solid ${on || indeterminate ? 'var(--accent)' : 'var(--border-strong)'}`,
      background: on || indeterminate ? 'var(--accent)' : 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
    }}>{on ? <Icon name="check" size={12} /> : indeterminate ? <span style={{ width: 8, height: 2, background: '#fff', borderRadius: 1 }} /> : null}</span>
  )
}

export default function ReportPanel({ terms, opts, variantB }: { terms: NoteTerms; opts: RunOpts; variantB?: NoteTerms | null }) {
  const { t, lang } = useI18n()
  const toast = useToast()
  const { start: startTour } = useTour()
  // Include the A/B comparison in the PDF (only offered once a Note B is set up
  // in the Compare tab). Default on when B exists, so building the report after a
  // comparison carries it through.
  const [compareOn, setCompareOn] = useState(true)
  const hasLive = !!terms.issue_date
  const groups = useMemo(() => TREE.filter((g) => g.key !== 'live' || hasLive), [hasLive])
  const allKeys = useMemo(() => groups.flatMap((g) => g.items.map((i) => i[0])), [groups])

  // A saved custom selection (persisted) is restored on load, so the user's own
  // section choice survives across sessions.
  const savedCustom = useMemo(() => loadCustom(), [])
  const [sel, setSel] = useState<Set<string>>(() =>
    new Set(savedCustom ? savedCustom.filter((k) => allKeys.includes(k)) : allKeys))
  const [preset, setPreset] = useState<Preset>(savedCustom ? 'custom' : 'full')
  // Bumped when a preset definition is saved/reset — preset definitions live in
  // localStorage, so this is what tells the memo below to re-read them.
  const [presetRev, setPresetRev] = useState(0)
  const [brandOpen, setBrandOpen] = useState(false)
  const [brand, setBrand] = useState<Branding>({})
  const [presets, setPresets] = useState<{ file: string; firm_name: string }[]>([])
  // The user's own folder of branding JSONs (auto-detected), alongside the repo presets.
  const brandFolder = useLocalFolder('branding')
  const [brandLocalName, setBrandLocalName] = useState<string | null>(null)
  const [brandSaving, setBrandSaving] = useState(false)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const logoRef = useRef<HTMLInputElement>(null)
  const altLogoRef = useRef<HTMLInputElement>(null)
  const sigilRef = useRef<HTMLInputElement>(null)
  const fillerRef = useRef<HTMLInputElement>(null)
  const brandCfgRef = useRef<HTMLInputElement>(null)
  const titleFontRef = useRef<HTMLInputElement>(null)
  const bodyFontRef = useRef<HTMLInputElement>(null)

  useEffect(() => { api.brandingList().then(setPresets).catch(() => {}) }, [])

  // Apply a branding config dict; flatten {en,es} title/footer/disclaimer to the
  // active lang for the editable fields while keeping every other key (colours,
  // logo, website, cover images, fonts). Shared by the preset picker and the
  // manual JSON upload.
  const applyBranding = (b: Record<string, any>) => {
    const flat = (v: unknown) => (v && typeof v === 'object' ? ((v as any)[lang] ?? (v as any).en ?? '') : v)
    setBrand({
      ...b,
      report_title: flat(b.report_title),
      footer_note: flat(b.footer_note),
      disclaimer_body: flat(b.disclaimer_body),
    } as Branding)
  }
  // Load a bundled branding preset auto-discovered from the branding/ folder.
  const loadPreset = async (file: string) => {
    if (!file) return
    setBrandLocalName(null)
    try { applyBranding(await api.branding(file) as Record<string, any>) } catch { /* ignore */ }
  }
  // Manual fallback: upload a branding config JSON when it isn't auto-detected
  // (e.g. a local/gitignored brand config that never shipped with the app).
  const onUploadBranding = (file: File | undefined) => {
    if (!file) return
    setBrandLocalName(null)
    const r = new FileReader()
    r.onload = () => {
      try { applyBranding(JSON.parse(String(r.result))); setError('') }
      catch { setError(t('brand_upload_bad')) }
    }
    r.readAsText(file)
  }
  // Save the branding straight back into the connected folder — overwriting the
  // file it was loaded from, or creating one named after the firm. Mirrors the
  // note-config save in the setup rail.
  const saveBrandingToFolder = async () => {
    setBrandSaving(true)
    try {
      const saved = await brandFolder.save(brandLocalName ?? (brand.firm_name || 'branding'), brand)
      setBrandLocalName(saved)
      toast.push({ title: t('brand_saved'), sub: `${saved}.json · ${brandFolder.folder}`, tone: 'accent', icon: 'check' })
    } catch {
      toast.push({ title: t('cfg_save_failed'), sub: t('cfg_save_failed_sub'), tone: 'red', icon: 'info' })
    } finally { setBrandSaving(false) }
  }
  // Download the current branding as a self-contained JSON — logo, cover sigil,
  // background image, fonts and colours are all already base64-embedded in
  // `brand`, so the file is portable and reloads identically (no external assets).
  const downloadBranding = () => {
    const json = JSON.stringify(brand, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const fname = `${(brand.firm_name || 'branding').replace(/[^A-Za-z0-9]+/g, '_').toLowerCase()}_branding.json`
    const a = document.createElement('a')
    a.href = url; a.download = fname
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
    toast.push({ title: t('brand_downloaded'), sub: fname, tone: 'accent' })
  }

  const lab = (en: string, es: string) => (lang === 'es' ? es : en)
  // Editing sections under an audience preset REDEFINES that preset (once saved)
  // rather than silently dropping to "custom" — the preset is the user's own
  // template. `full` has nothing to redefine, so editing it means going custom.
  const afterEdit = () => { if (preset === 'full') setPreset('custom'); setStatus('idle') }
  const toggle = (k: string) => {
    setSel((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n })
    afterEdit()
  }
  const toggleGroup = (g: Group) => {
    const ks = g.items.map((i) => i[0])
    const allOn = ks.every((k) => sel.has(k))
    setSel((p) => { const n = new Set(p); ks.forEach((k) => allOn ? n.delete(k) : n.add(k)); return n })
    afterEdit()
  }
  // Apply a named preset: select its sections (intersected with what's available).
  // "Custom" restores the saved custom selection (or, if none, keeps the current
  // one so the user can start fine-tuning from where they are).
  const applyPreset = (p: Preset) => {
    setPreset(p)
    setStatus('idle')
    if (p === 'custom') {
      const saved = loadCustom()
      if (saved) setSel(new Set(saved.filter((k) => allKeys.includes(k))))
      return
    }
    setSel(new Set(p === 'full' ? allKeys : presetKeys(p).filter((k) => allKeys.includes(k))))
  }

  // Is the current selection different from what the active preset is defined as?
  // Only sections actually available for this note are compared, so a note with
  // no live data doesn't read as "modified" just for lacking that group.
  const presetDef = useMemo(
    () => (preset === 'full' || preset === 'custom')
      ? null : new Set(presetKeys(preset).filter((k) => allKeys.includes(k))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [preset, allKeys, presetRev])
  const presetDirty = !!presetDef
    && (presetDef.size !== sel.size || [...sel].some((k) => !presetDef.has(k)))
  const savePreset = () => {
    if (preset === 'full' || preset === 'custom') return
    // Merge: keep any keys the definition had that this note can't offer (e.g.
    // live sections on a note with no issue date), so saving from a note without
    // them doesn't quietly strip them from the preset for every other note.
    const unavailable = presetKeys(preset).filter((k) => !allKeys.includes(k))
    savePresetOverride(preset, [...unavailable, ...allKeys.filter((k) => sel.has(k))])
    setPresetRev((r) => r + 1)
    toast.push({ title: t('rep_preset_saved', { name: t(`rep_preset_${preset}`) }), tone: 'accent', icon: 'check' })
  }
  const resetPreset = () => {
    if (preset === 'full' || preset === 'custom') return
    resetPresetOverride(preset)
    setPresetRev((r) => r + 1)
    setSel(new Set(presetKeys(preset).filter((k) => allKeys.includes(k))))
  }

  // Persist the custom selection whenever it changes, so it's there next session.
  useEffect(() => {
    if (preset !== 'custom') return
    try { localStorage.setItem(CUSTOM_LS, JSON.stringify([...sel])) } catch { /* ignore */ }
  }, [sel, preset])
  const setBrandField = <K extends keyof Branding>(k: K, v: Branding[K]) => setBrand((b) => {
    const empty = v === '' || v == null || (Array.isArray(v) && v.length === 0)
    return { ...b, [k]: empty ? undefined : v }
  })
  const onImage = (field: keyof Branding, file: File | undefined) => {
    if (!file) return
    const r = new FileReader(); r.onload = () => setBrandField(field, String(r.result)); r.readAsDataURL(file)
  }
  // Append one or more uploaded photos to the report-image pool
  // (`filler_images_base64`) — the same pool the cover, back page and mid-report
  // filler bands draw from. Lets a brand add its own imagery without Pexels.
  const onFillerUpload = (files: FileList | null) => {
    if (!files || !files.length) return
    Promise.all(Array.from(files).map((f) => new Promise<string>((res, rej) => {
      const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = rej; r.readAsDataURL(f)
    }))).then((urls) => setBrand((b) => {
      const cur = (b.filler_images_base64 as string[] | undefined) ?? []
      const room = Math.max(0, maxPhotos - cur.length)      // respect the report's photo capacity
      return { ...b, filler_images_base64: [...cur, ...urls.slice(0, room)] }
    })).catch(() => {})
  }
  // KEY TERMS the user can show in the strip along the bottom of the COVER page.
  // Order here is the order they render; only the first ~4 fit alongside the
  // website. Absent selection → the PDF's default three; an explicit empty
  // array → the strip is hidden entirely.
  const COVER_METRIC_KEYS = ['maturity', 'coupon_pa', 'coupon_barrier', 'autocall_barrier', 'knock_in_barrier', 'issue_date', 'issuer'] as const
  const COVER_METRIC_DEFAULT = ['coupon_pa', 'maturity', 'knock_in_barrier']
  const COVER_METRIC_MAX = 4
  const metricLabel = (k: string) => k === 'issuer' ? t('issuer_name') : t(k)
  const coverMetricsSel = (brand.cover_metrics as string[] | undefined) ?? COVER_METRIC_DEFAULT
  const toggleCoverMetric = (k: string) => {
    const base = (brand.cover_metrics as string[] | undefined) ?? COVER_METRIC_DEFAULT
    const next = base.includes(k) ? base.filter((m) => m !== k) : [...COVER_METRIC_KEYS].filter((m) => base.includes(m) || m === k)
    // Write straight to state (NOT setBrandField, which collapses an empty array
    // to undefined) so an empty selection sticks and the strip can be fully off —
    // the PDF treats [] as "hide the strip" and only a missing value as default.
    setBrand((b) => ({ ...b, cover_metrics: next }))
  }
  // Embed TTF/OTF font files (base64, keyed by inferred style) into the config so
  // the fonts travel with it and render on the deploy. Style is read off the
  // filename (…Bold, …Italic, …BoldItalic, else Regular) — same convention as
  // fonts/brand/<Name>-<Style>.ttf.
  const styleOf = (name: string) => {
    const n = name.toLowerCase().replace(/[^a-z]/g, '')
    if (n.includes('bold') && n.includes('italic')) return 'BoldItalic'
    if (n.includes('italic')) return 'Italic'
    if (n.includes('bold')) return 'Bold'
    return 'Regular'
  }
  const onFontFiles = (field: 'title_font_files' | 'body_font_files', files: FileList | null) => {
    if (!files || !files.length) return
    const acc: Record<string, string> = { ...((brand[field] as Record<string, string>) ?? {}) }
    let pending = files.length
    Array.from(files).forEach((f) => {
      const r = new FileReader()
      r.onload = () => {
        const s = String(r.result)
        acc[styleOf(f.name)] = s.includes(',') ? s.split(',')[1] : s
        if (--pending === 0) setBrand((b) => ({ ...b, [field]: acc }))
      }
      r.readAsDataURL(f)
    })
  }
  const fontCount = (field: 'title_font_files' | 'body_font_files') =>
    Object.keys((brand[field] as Record<string, string>) ?? {}).length

  const generate = async () => {
    setStatus('running'); setError('')
    try {
      const branding = Object.values(brand).some(Boolean) ? brand : null
      // Sync render on purpose: on Cloud Run, CPU is only allocated while a
      // request is in flight, so a background job (the /api/report/start +
      // polling flow) starves and never finishes. The async endpoints still
      // exist for deployments with always-allocated CPU.
      const res = await api.report({
        terms, sections: [...sel], lang, branding,
        n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine,
        compare_terms: compareOn && variantB ? variantB : null,
        // Stamps the report type on the cover. "custom" has no audience to name,
        // so it goes out untyped rather than labelled "Custom report".
        report_kind: preset === 'custom' ? null : preset,
      })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const filename = filenameFrom(res, 'structured_note_report.pdf')
      const a = document.createElement('a'); a.href = url; a.download = filename
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
      setStatus('done')
      const mb = blob.size / 1048576
      const size = mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(blob.size / 1024))} KB`
      toast.push({ title: t('report_downloaded'), sub: `${filename} · ${size}` })
    } catch (e) { setError(String(e instanceof Error ? e.message : e)); setStatus('error') }
  }

  const none = sel.size === 0
  // How many report photos can actually appear: cover + back + ~one filler band
  // per couple of included sections (pages). A rough but sensible cap so the user
  // doesn't pick more photos than the report will ever show. Clamped to [4, 12].
  const maxPhotos = Math.max(4, Math.min(12, 2 + Math.ceil(sel.size / 2)))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('report_intro')}</div>
        <button className="btn btn--ghost" style={{ padding: '7px 12px', whiteSpace: 'nowrap', flexShrink: 0 }}
                onClick={() => { setBrandOpen(true); startTour(reportTour(t)) }}>
          <Icon name="info" size={14} /> {t('rep_tutorial')}
        </button>
      </div>

      <Panel title={t('report_sections')}>
        <div style={{ marginBottom: 18 }} data-tour="rep-presets">
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 9 }}>{t('rep_preset')}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {PRESET_ORDER.map((p) => (
              <button key={p} type="button" className="preset-pill" data-on={preset === p}
                      title={t(`rep_preset_${p}_desc`)} onClick={() => applyPreset(p)}>
                {t(`rep_preset_${p}`)}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 9, lineHeight: 1.5 }}>{t(`rep_preset_${preset}_desc`)}</div>
          {/* Audience presets are the user's own templates: tick the sections you
              want below, then save them INTO the preset. */}
          {presetDef && (presetDirty || isPresetCustomised(preset)) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              {presetDirty && (
                <button type="button" className="btn" style={{ padding: '5px 11px', fontSize: 12 }} onClick={savePreset}>
                  <Icon name="save" size={13} /> {t('rep_preset_save', { name: t(`rep_preset_${preset}`) })}
                </button>
              )}
              {isPresetCustomised(preset) && (
                <button type="button" className="btn btn--ghost" style={{ padding: '5px 11px', fontSize: 12 }} onClick={resetPreset}>
                  <Icon name="refresh" size={13} /> {t('rep_preset_reset')}
                </button>
              )}
              <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                {presetDirty ? t('rep_preset_dirty') : t('rep_preset_customised')}
              </span>
            </div>
          )}
        </div>
        {variantB && (
          <div style={{ marginBottom: 18, padding: '12px 14px', borderRadius: 10,
                        background: 'var(--accent-weak)', border: '1px solid var(--accent)' }}>
            <button onClick={() => setCompareOn((v) => !v)}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0, width: '100%' }}>
              <Check on={compareOn} />
              <span style={{ fontSize: 13.5, fontWeight: 700 }}>{t('rep_include_compare')}</span>
            </button>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 6, marginLeft: 28, lineHeight: 1.5 }}>
              {t('rep_compare_hint', { name: variantB.name || t('cmp_note_b') })}
            </div>
          </div>
        )}
        <div data-tour="rep-sections" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '4px 28px' }}>
          {groups.map((g) => {
            const ks = g.items.map((i) => i[0])
            const onCount = ks.filter((k) => sel.has(k)).length
            return (
              <div key={g.key} style={{ marginBottom: 14 }}>
                <button onClick={() => toggleGroup(g)}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '6px 0', width: '100%' }}>
                  <Check on={onCount === ks.length} indeterminate={onCount > 0 && onCount < ks.length} />
                  <span style={{ fontSize: 13.5, fontWeight: 700 }}>{lab(g.en, g.es)}</span>
                </button>
                {g.items.map(([k, en, es]) => (
                  <button key={k} onClick={() => toggle(k)}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '5px 0 5px 26px', width: '100%' }}>
                    <Check on={sel.has(k)} />
                    <span style={{ fontSize: 13, color: 'var(--text)' }}>{lab(en, es)}</span>
                  </button>
                ))}
              </div>
            )
          })}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 6, lineHeight: 1.5 }}>{t('report_note')}</div>
      </Panel>

      {/* Branding (collapsible) */}
      <Panel pad={0}>
        <button onClick={() => setBrandOpen((v) => !v)}
          style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 9, background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '14px 16px', color: 'var(--text)' }}>
          <span style={{ transition: 'transform 0.15s', transform: brandOpen ? 'rotate(90deg)' : 'none', color: 'var(--text-faint)' }}>›</span>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{t('rep_branding')}</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)', marginLeft: 8 }}>{t('rep_branding_opt')}</span>
        </button>
        {brandOpen && (
          <div style={{ padding: '0 16px 12px', display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            {(presets.length > 0 || brandFolder.files.length > 0 || brandFolder.supported) && (
              <Field label={t('brand_preset')}>
                <Select value="" placeholder={t('brand_preset_ph')} ariaLabel={t('brand_preset')}
                        options={[
                          ...brandFolder.files.map((f) => ({ value: `local:${f.name}`, label: `${f.name} ${t('folder_tag')}` })),
                          ...presets.map((p) => ({ value: p.file, label: p.firm_name })),
                        ]}
                        onChange={(v) => {
                          if (v.startsWith('local:')) {
                            const f = brandFolder.files.find((f) => `local:${f.name}` === v)
                            if (f) { setBrandLocalName(f.name); applyBranding(f.raw as Record<string, unknown>) }
                          } else loadPreset(v)
                        }} />
                <FolderConnect fld={brandFolder} />
              </Field>
            )}
            <Field label={t('brand_upload_cfg')}>
              <button className="btn" style={{ padding: '7px 12px' }} onClick={() => brandCfgRef.current?.click()}>
                <Icon name="upload" size={13} /> {t('brand_upload_cfg_btn')}
              </button>
              <input ref={brandCfgRef} type="file" accept="application/json,.json" style={{ display: 'none' }}
                     onChange={(e) => { onUploadBranding(e.target.files?.[0]); e.target.value = '' }} />
            </Field>
            <Field label={t('brand_save_cfg')}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button className="btn" style={{ padding: '7px 12px' }} onClick={downloadBranding}>
                  <Icon name="download" size={13} /> {t('brand_save_cfg_btn')}
                </button>
                {brandFolder.canSave && (
                  <button className="btn" style={{ padding: '7px 12px', maxWidth: '100%', overflow: 'hidden' }}
                          disabled={brandSaving} onClick={saveBrandingToFolder}
                          title={brandLocalName ? t('cfg_save_over_hint', { name: brandLocalName }) : t('cfg_save_to_folder_hint')}>
                    <Icon name={brandSaving ? 'spinner' : 'save'} size={13} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
                      {brandLocalName ? t('cfg_save_changes', { name: brandLocalName }) : t('brand_save_to_folder_btn')}
                    </span>
                  </button>
                )}
              </div>
            </Field>
          </div>
        )}
        {brandOpen && (
          <div style={{ padding: '0 16px 18px', display: 'flex', flexDirection: 'column', gap: 18 }}>
            {/* Core identity (firm, logo, colours, fonts) — the "Brand it" tour step. */}
            <div data-tour="rep-branding" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            {/* Identity */}
            <div>
              <SubHead>{t('brand_identity')}</SubHead>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
                <Field label={t('brand_firm')}><input type="text" value={brand.firm_name ?? ''} onChange={(e) => setBrandField('firm_name', e.target.value)} /></Field>
                <Field label={t('brand_title')}><input type="text" value={brand.report_title ?? ''} onChange={(e) => setBrandField('report_title', e.target.value)} /></Field>
                <Field label={t('brand_website')}><input type="text" placeholder="www.firm.com" value={brand.website ?? ''} onChange={(e) => setBrandField('website', e.target.value)} /></Field>
                <Field label={t('brand_contact')}><input type="text" placeholder="research@firm.com" value={brand.contact ?? ''} onChange={(e) => setBrandField('contact', e.target.value)} /></Field>
                <Field label={t('brand_logo')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="btn" style={{ padding: '7px 12px' }} onClick={() => logoRef.current?.click()}><Icon name="upload" size={13} /> {t('det_upload_logo')}</button>
                    <ImgPreview src={brand.logo_base64} style={{ height: 26, borderRadius: 5 }} />
                    {brand.logo_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('logo_base64', '')}>{t('det_reset_logo')}</button>}
                    <input ref={logoRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onImage('logo_base64', e.target.files?.[0])} />
                  </div>
                </Field>
              </div>
            </div>

            {/* Colours */}
            <div>
              <SubHead>{t('brand_colors')}</SubHead>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 14 }}>
                <Swatch label={t('brand_primary')}   value={brand.primary_color} fallback="#1a2e4a" onChange={(v) => setBrandField('primary_color', v)} />
                <Swatch label={t('brand_accent')}    value={brand.accent_color} fallback="#2563eb" onChange={(v) => setBrandField('accent_color', v)} />
                <Swatch label={t('brand_secondary')} value={brand.chart_secondary_color} fallback="#c69426" onChange={(v) => setBrandField('chart_secondary_color', v)} />
                <Swatch label={t('brand_rule')}      value={brand.section_rule_color} fallback="#2563eb" onChange={(v) => setBrandField('section_rule_color', v)} />
                <Swatch label={t('brand_panel')}     value={brand.panel_color} fallback="#eaf1f8" onChange={(v) => setBrandField('panel_color', v)} />
              </div>
            </div>

            {/* Typography */}
            <div>
              <SubHead>{t('brand_typography')}</SubHead>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
                <Field label={t('brand_title_font')}>
                  <input type="text" placeholder="IBM Plex Sans" value={brand.title_font ?? ''} onChange={(e) => setBrandField('title_font', e.target.value)} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                    <button className="btn" style={{ padding: '6px 10px', fontSize: 11.5 }} onClick={() => titleFontRef.current?.click()}><Icon name="upload" size={12} /> {t('brand_embed_fonts')}</button>
                    {fontCount('title_font_files') > 0 && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('brand_fonts_n', { n: fontCount('title_font_files') })}</span>}
                    {fontCount('title_font_files') > 0 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11 }} onClick={() => setBrand((b) => ({ ...b, title_font_files: undefined }))}>{t('det_reset_logo')}</button>}
                    <input ref={titleFontRef} type="file" accept=".ttf,.otf" multiple style={{ display: 'none' }} onChange={(e) => { onFontFiles('title_font_files', e.target.files); e.target.value = '' }} />
                  </div>
                </Field>
                <Field label={t('brand_body_font')}>
                  <input type="text" placeholder="IBM Plex Sans" value={brand.body_font ?? ''} onChange={(e) => setBrandField('body_font', e.target.value)} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                    <button className="btn" style={{ padding: '6px 10px', fontSize: 11.5 }} onClick={() => bodyFontRef.current?.click()}><Icon name="upload" size={12} /> {t('brand_embed_fonts')}</button>
                    {fontCount('body_font_files') > 0 && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('brand_fonts_n', { n: fontCount('body_font_files') })}</span>}
                    {fontCount('body_font_files') > 0 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11 }} onClick={() => setBrand((b) => ({ ...b, body_font_files: undefined }))}>{t('det_reset_logo')}</button>}
                    <input ref={bodyFontRef} type="file" accept=".ttf,.otf" multiple style={{ display: 'none' }} onChange={(e) => { onFontFiles('body_font_files', e.target.files); e.target.value = '' }} />
                  </div>
                </Field>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 5 }}>{t('brand_font_hint')}</div>
            </div>
            </div>{/* /rep-branding core */}

            {/* Cover */}
            <div>
              <SubHead>{t('brand_cover')}</SubHead>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
                <Field label={t('brand_alt_logo')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="btn" style={{ padding: '7px 12px' }} onClick={() => altLogoRef.current?.click()}><Icon name="upload" size={13} /> {t('det_upload_logo')}</button>
                    <ImgPreview src={brand.cover_logo_base64} style={{ height: 26, borderRadius: 5, background: brand.primary_color ?? '#1a2e4a', padding: 2 }} />
                    {brand.cover_logo_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('cover_logo_base64', '')}>{t('det_reset_logo')}</button>}
                    <input ref={altLogoRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onImage('cover_logo_base64', e.target.files?.[0])} />
                  </div>
                </Field>
                <Field label={t('brand_cover_sigil')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="btn" style={{ padding: '7px 12px' }} onClick={() => sigilRef.current?.click()}><Icon name="upload" size={13} /> {t('det_upload_logo')}</button>
                    <ImgPreview src={brand.cover_sigil_base64} style={{ height: 26, borderRadius: 5, background: brand.primary_color ?? '#1a2e4a', padding: 2 }} />
                    {brand.cover_sigil_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('cover_sigil_base64', '')}>{t('det_reset_logo')}</button>}
                    <input ref={sigilRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onImage('cover_sigil_base64', e.target.files?.[0])} />
                  </div>
                </Field>
                {/* The cover (1st pick) and back-page (2nd pick) photos are chosen
                    in the report-photo library below — no separate cover/back
                    upload here, which used to compete with that pool for the same
                    two slots. Overlay colour/opacity below still tint whatever the
                    library resolves as the cover. */}
                <Swatch label={t('brand_overlay_color')} value={brand.cover_overlay_color} fallback={brand.primary_color ?? '#1a2e4a'} onChange={(v) => setBrandField('cover_overlay_color', v)} />
                <Field label={t('brand_overlay_opacity')}>
                  <input type="number" min={0} max={1} step={0.05} placeholder="0.55"
                         value={brand.cover_overlay_opacity != null ? String(brand.cover_overlay_opacity) : ''}
                         onChange={(e) => setBrandField('cover_overlay_opacity', e.target.value)} />
                </Field>
              </div>
              {/* Report-photo library — professional photos by sector, suggested
                  from the note's underlyings. MULTI-select: the chosen pool drives
                  the cover, the back page and the empty-space filler bands (each
                  gap cycles to the next photo). Overlay still applies. */}
              <div style={{ marginTop: 14 }} data-tour="rep-photos">
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('cover_lib')}</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, lineHeight: 1.5 }}>{t('cover_lib_multi_hint')}</div>
                {/* Upload your own report photos straight into the pool — works
                    independently of the Pexels library. */}
                <div style={{ marginBottom: 8 }}>
                  <button className="btn" style={{ padding: '7px 12px' }} onClick={() => fillerRef.current?.click()}>
                    <Icon name="upload" size={13} /> {t('rep_photos_upload')}
                  </button>
                  <input ref={fillerRef} type="file" accept="image/*" multiple style={{ display: 'none' }}
                         onChange={(e) => { onFillerUpload(e.target.files); e.target.value = '' }} />
                </div>
                <CoverPhotoPicker terms={terms} max={maxPhotos}
                                  selected={brand.filler_images_base64 ?? []}
                                  onChange={(urls) => setBrandField('filler_images_base64', urls)} />
              </div>

              {/* Cover key terms — pick which metrics show in the strip at the
                  bottom of the cover page. Only the first few fit; extras beyond
                  the cap are dimmed to show they won't render. */}
              <div style={{ marginTop: 16 }} data-tour="rep-metrics">
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('cover_metrics')}</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, lineHeight: 1.5 }}>{t('cover_metrics_hint')}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                  {COVER_METRIC_KEYS.map((k) => {
                    const on = coverMetricsSel.includes(k)
                    const overCap = on && coverMetricsSel.indexOf(k) >= COVER_METRIC_MAX
                    return (
                      <button key={k} type="button" className="preset-pill" data-on={on}
                              title={overCap ? t('cover_metrics_over') : undefined}
                              style={overCap ? { opacity: 0.45 } : undefined}
                              onClick={() => toggleCoverMetric(k)}>
                        {metricLabel(k)}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>

            {/* Legal text */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 14 }}>
              <Field label={t('brand_footer')}><input type="text" value={brand.footer_note ?? ''} onChange={(e) => setBrandField('footer_note', e.target.value)} /></Field>
              <Field label={t('brand_disclaimer')}>
                <textarea value={brand.disclaimer_body ?? ''} onChange={(e) => setBrandField('disclaimer_body', e.target.value)}
                  style={{ width: '100%', minHeight: 84, resize: 'vertical', fontFamily: 'inherit', fontSize: 12.5, lineHeight: 1.5, padding: '9px 11px', borderRadius: 9, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)' }} />
              </Field>
            </div>
          </div>
        )}
      </Panel>

      <div data-tour="rep-generate" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <button className="btn btn--primary" onClick={generate} disabled={status === 'running' || none} style={{ padding: '12px 22px', fontSize: 14 }}>
          <Icon name={status === 'running' ? 'spinner' : 'chart'} size={16} />
          {status === 'running' ? t('report_generating') : t('report_generate')}
        </button>
        {none && <span style={{ fontSize: 12.5, color: 'var(--amber)' }}>{t('report_select_one')}</span>}
        {status === 'done' && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--green)' }}><Icon name="check" size={15} /> {t('report_downloaded')}</span>}
        {status === 'error' && <span style={{ fontSize: 12.5, color: 'var(--red)' }}><strong>{t('error')}.</strong> {error}</span>}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ fontSize: 11.5, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  )
}

function SubHead({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-faint)', marginBottom: 10 }}>{children}</div>
  )
}

/** Colour field: a swatch that opens the native picker + a hex readout. */
function Swatch({ label, value, fallback, onChange }: { label: string; value?: string; fallback: string; onChange: (v: string) => void }) {
  const v = value ?? fallback
  return (
    <Field label={label}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input type="color" value={v} onChange={(e) => onChange(e.target.value)}
          style={{ height: 34, width: 44, padding: 3, flexShrink: 0, cursor: 'pointer' }} />
        <input type="text" value={value ?? ''} placeholder={fallback} onChange={(e) => onChange(e.target.value)}
          className="mono" style={{ fontSize: 12, padding: '7px 9px' }} />
      </div>
    </Field>
  )
}
