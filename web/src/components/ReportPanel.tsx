import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { useToast } from './Toast'
import Panel from './Panel'
import Icon from './Icon'
import { Select } from './fields'
import FolderConnect from './FolderConnect'
import CoverPhotoPicker from './CoverPhotoPicker'
import { useLocalFolder } from '../lib/localFolder'
import type { Branding, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'

type Status = 'idle' | 'running' | 'done' | 'error'
type Item = [key: string, en: string, es: string]
type Group = { key: string; en: string; es: string; items: Item[] }

const TREE: Group[] = [
  { key: 'note', en: 'Note details', es: 'Detalle de la nota', items: [
    ['cover', 'Cover page', 'Portada'],
    ['note_description', 'Note description', 'Descripción de la nota'],
    ['note_diagram', 'Structure diagram', 'Diagrama de la estructura'],
    ['note_terms', 'Note terms', 'Términos'],
    ['obs_schedule', 'Observation schedule', 'Calendario de observaciones'],
    ['issuer_info', 'Issuer information', 'Información del emisor'],
    ['underlying_breakdown', 'Underlying breakdown', 'Análisis de subyacentes'],
  ] },
  { key: 'mc', en: 'Monte Carlo', es: 'Monte Carlo', items: [
    ['mc_metrics', 'Summary & metrics', 'Resumen y métricas'],
    ['mc_outcome', 'Outcome breakdown', 'Distribución de resultados'],
    ['mc_autocall', 'Autocall by period', 'Autocall por período'],
    ['mc_irr', 'IRR distribution', 'Distribución de TIR'],
    ['mc_wof', 'Worst-of fan chart', 'Abanico del peor de'],
    ['mc_sample', 'Sample paths', 'Trayectorias de muestra'],
    ['mc_fans', 'Per-underlying fans', 'Abanicos por activo'],
    ['calib_corr', 'Correlation diagnostics', 'Diagnóstico de correlación'],
    ['calib_table', 'Calibration table', 'Tabla de calibración'],
  ] },
  { key: 'bt', en: 'Historical backtest', es: 'Backtest histórico', items: [
    ['bt_metrics', 'Outcome metrics', 'Métricas de resultados'],
    ['bt_outcome', 'Outcome distribution', 'Distribución de resultados'],
    ['bt_pie', 'Worst-asset pie', 'Peor activo'],
    ['bt_irr', 'IRR scatter', 'Dispersión de TIR'],
    ['bt_prices', 'Price history', 'Histórico de precios'],
  ] },
  { key: 'live', en: 'Current performance', es: 'Rendimiento actual', items: [
    ['live_metrics', 'Live metrics', 'Métricas en vivo'],
    ['live_asset_table', 'Per-asset table', 'Tabla por activo'],
    ['live_obs_table', 'Observation history', 'Historial de observaciones'],
    ['live_chart', 'Performance chart', 'Gráfico de rendimiento'],
  ] },
]

// Report presets — one click selects a sensible set of sections for an audience.
// Keys are intersected with what's actually available (e.g. the live group only
// when the note has an issue date). "full" / "custom" are handled specially.
// "Custom" is the mode any manual toggle drops into, and it is persisted.
const PRESET_KEYS: Record<string, string[]> = {
  // Client fact sheet — what the note is: terms, structure, underlyings. No
  // simulation / backtest analysis.
  client: ['cover', 'note_description', 'note_diagram', 'note_terms', 'obs_schedule', 'issuer_info', 'underlying_breakdown'],
  // Bare term sheet — the legal essentials only.
  term_sheet: ['cover', 'note_terms', 'note_diagram', 'obs_schedule', 'issuer_info'],
  // Sales one-pager — the appealing bits: structure, underlyings and headline
  // results, without the heavy diagnostics.
  marketing: ['cover', 'note_description', 'note_diagram', 'underlying_breakdown', 'mc_metrics', 'mc_outcome', 'live_metrics', 'live_chart'],
  // Investment-committee pack — a balanced decision view.
  ic: ['note_terms', 'note_diagram', 'underlying_breakdown', 'mc_metrics', 'mc_outcome', 'mc_autocall', 'mc_wof', 'bt_metrics', 'bt_outcome', 'live_metrics'],
  // Risk analyst — the full quantitative analysis plus terms for context. Skips
  // the branded cover and the marketing description.
  analyst: ['note_terms', 'note_diagram', 'obs_schedule', 'issuer_info', 'underlying_breakdown',
            'mc_metrics', 'mc_outcome', 'mc_autocall', 'mc_irr', 'mc_wof', 'mc_sample', 'mc_fans', 'calib_corr', 'calib_table',
            'bt_metrics', 'bt_outcome', 'bt_pie', 'bt_irr', 'bt_prices',
            'live_metrics', 'live_asset_table', 'live_obs_table', 'live_chart'],
  // Model review — Monte Carlo internals, calibration and correlation diagnostics.
  quant: ['note_terms', 'mc_metrics', 'mc_irr', 'mc_wof', 'mc_fans', 'calib_corr', 'calib_table'],
}
const PRESET_ORDER = ['full', 'client', 'term_sheet', 'marketing', 'ic', 'analyst', 'quant', 'custom'] as const
type Preset = (typeof PRESET_ORDER)[number]
const CUSTOM_LS = 'mercator_report_custom'
const loadCustom = (): string[] | null => {
  try { const r = localStorage.getItem(CUSTOM_LS); return r ? (JSON.parse(r) as string[]) : null } catch { return null }
}

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get('Content-Disposition') || ''
  const m = cd.match(/filename="?([^"]+)"?/)
  return m ? m[1] : fallback
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

export default function ReportPanel({ terms, opts }: { terms: NoteTerms; opts: RunOpts }) {
  const { t, lang } = useI18n()
  const toast = useToast()
  const hasLive = !!terms.issue_date
  const groups = useMemo(() => TREE.filter((g) => g.key !== 'live' || hasLive), [hasLive])
  const allKeys = useMemo(() => groups.flatMap((g) => g.items.map((i) => i[0])), [groups])

  // A saved custom selection (persisted) is restored on load, so the user's own
  // section choice survives across sessions.
  const savedCustom = useMemo(() => loadCustom(), [])
  const [sel, setSel] = useState<Set<string>>(() =>
    new Set(savedCustom ? savedCustom.filter((k) => allKeys.includes(k)) : allKeys))
  const [preset, setPreset] = useState<Preset>(savedCustom ? 'custom' : 'full')
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
  const coverImgRef = useRef<HTMLInputElement>(null)
  const sigilRef = useRef<HTMLInputElement>(null)
  const backImgRef = useRef<HTMLInputElement>(null)
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
  const toggle = (k: string) => { setSel((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n }); setPreset('custom'); setStatus('idle') }
  const toggleGroup = (g: Group) => {
    const ks = g.items.map((i) => i[0])
    const allOn = ks.every((k) => sel.has(k))
    setSel((p) => { const n = new Set(p); ks.forEach((k) => allOn ? n.delete(k) : n.add(k)); return n })
    setPreset('custom')
    setStatus('idle')
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
    const keys = p === 'full' ? allKeys : (PRESET_KEYS[p] ?? []).filter((k) => allKeys.includes(k))
    setSel(new Set(keys))
  }

  // Persist the custom selection whenever it changes, so it's there next session.
  useEffect(() => {
    if (preset !== 'custom') return
    try { localStorage.setItem(CUSTOM_LS, JSON.stringify([...sel])) } catch { /* ignore */ }
  }, [sel, preset])
  const setBrandField = (k: keyof Branding, v: string) => setBrand((b) => ({ ...b, [k]: v || undefined }))
  const onImage = (field: keyof Branding, file: File | undefined) => {
    if (!file) return
    const r = new FileReader(); r.onload = () => setBrandField(field, String(r.result)); r.readAsDataURL(file)
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
      const res = await api.report({
        terms, sections: [...sel], lang, branding,
        n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine,
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('report_intro')}</div>

      <Panel title={t('report_sections')}>
        <div style={{ marginBottom: 18 }}>
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
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '4px 28px' }}>
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
                  <button className="btn" style={{ padding: '7px 12px' }} disabled={brandSaving} onClick={saveBrandingToFolder}
                          title={brandLocalName ? t('cfg_save_over_hint', { name: brandLocalName }) : t('cfg_save_to_folder_hint')}>
                    <Icon name={brandSaving ? 'spinner' : 'save'} size={13} /> {t('brand_save_to_folder_btn')}
                  </button>
                )}
              </div>
            </Field>
          </div>
        )}
        {brandOpen && (
          <div style={{ padding: '0 16px 18px', display: 'flex', flexDirection: 'column', gap: 18 }}>
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
                    {brand.logo_base64 && <img src={brand.logo_base64} alt="logo" style={{ height: 26, borderRadius: 5 }} />}
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

            {/* Cover */}
            <div>
              <SubHead>{t('brand_cover')}</SubHead>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
                <Field label={t('brand_alt_logo')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="btn" style={{ padding: '7px 12px' }} onClick={() => altLogoRef.current?.click()}><Icon name="upload" size={13} /> {t('det_upload_logo')}</button>
                    {brand.cover_logo_base64 && <img src={brand.cover_logo_base64} alt="alt logo" style={{ height: 26, borderRadius: 5, background: brand.primary_color ?? '#1a2e4a', padding: 2 }} />}
                    {brand.cover_logo_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('cover_logo_base64', '')}>{t('det_reset_logo')}</button>}
                    <input ref={altLogoRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onImage('cover_logo_base64', e.target.files?.[0])} />
                  </div>
                </Field>
                <Field label={t('brand_cover_sigil')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="btn" style={{ padding: '7px 12px' }} onClick={() => sigilRef.current?.click()}><Icon name="upload" size={13} /> {t('det_upload_logo')}</button>
                    {brand.cover_sigil_base64 && <img src={brand.cover_sigil_base64} alt="sigil" style={{ height: 26, borderRadius: 5, background: brand.primary_color ?? '#1a2e4a', padding: 2 }} />}
                    {brand.cover_sigil_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('cover_sigil_base64', '')}>{t('det_reset_logo')}</button>}
                    <input ref={sigilRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onImage('cover_sigil_base64', e.target.files?.[0])} />
                  </div>
                </Field>
                <Field label={t('brand_cover_image')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="btn" style={{ padding: '7px 12px' }} onClick={() => coverImgRef.current?.click()}><Icon name="upload" size={13} /> {t('brand_upload_image')}</button>
                    {brand.cover_image_base64 && <img src={brand.cover_image_base64} alt="cover" style={{ height: 26, borderRadius: 5 }} />}
                    {brand.cover_image_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('cover_image_base64', '')}>{t('det_reset_logo')}</button>}
                    <input ref={coverImgRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onImage('cover_image_base64', e.target.files?.[0])} />
                  </div>
                </Field>
                <Field label={t('brand_back_image')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="btn" style={{ padding: '7px 12px' }} onClick={() => backImgRef.current?.click()}><Icon name="upload" size={13} /> {t('brand_upload_image')}</button>
                    {brand.back_image_base64 && <img src={brand.back_image_base64} alt="back" style={{ height: 26, borderRadius: 5 }} />}
                    {brand.back_image_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('back_image_base64', '')}>{t('det_reset_logo')}</button>}
                    <input ref={backImgRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onImage('back_image_base64', e.target.files?.[0])} />
                  </div>
                </Field>
                <Swatch label={t('brand_overlay_color')} value={brand.cover_overlay_color} fallback={brand.primary_color ?? '#1a2e4a'} onChange={(v) => setBrandField('cover_overlay_color', v)} />
                <Field label={t('brand_overlay_opacity')}>
                  <input type="number" min={0} max={1} step={0.05} placeholder="0.55"
                         value={brand.cover_overlay_opacity != null ? String(brand.cover_overlay_opacity) : ''}
                         onChange={(e) => setBrandField('cover_overlay_opacity', e.target.value)} />
                </Field>
              </div>
              {/* Cover-photo library — professional photos by sector, suggested from
                  the note's underlyings. Sets the cover image (overlay still applies). */}
              <div style={{ marginTop: 14 }}>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('cover_lib')}</div>
                <CoverPhotoPicker terms={terms} onPick={(d) => setBrandField('cover_image_base64', d)} />
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

      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
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
