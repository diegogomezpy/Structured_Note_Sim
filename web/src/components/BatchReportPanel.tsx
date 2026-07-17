import { useEffect, useMemo, useState } from 'react'
import JSZip from 'jszip'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { useToast } from './Toast'
import Panel from './Panel'
import Icon from './Icon'
import { Select } from './fields'
import FolderConnect from './FolderConnect'
import CoverPhotoPicker from './CoverPhotoPicker'
import SectionTree from './SectionTree'
import { useLocalFolder, safeName } from '../lib/localFolder'
import { groupsFor, keysOf, keysForPreset, PRESET_ORDER, type Preset } from '../lib/reportSections'
import { autoIndustryPhotos, resolveSector, photoCapacity, type PhotoMode } from '../lib/batchReport'
import type { Branding, ConfigMeta, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'

type RowStatus = 'idle' | 'running' | 'done' | 'error'
type Lang = 'en' | 'es'
interface Row {
  id: number
  terms: NoteTerms
  sel: Set<string>
  preset: Preset
  lang: Lang
  photoMode: PhotoMode
  photos: string[]        // custom picks (data URLs)
  sector?: string         // resolved sector for the auto-mode label ('' = resolving)
  status: RowStatus
  error?: string
  expanded: boolean
  selected: boolean
}

let _rid = 0

// Presets offered as the default for new rows (drop the special "custom").
const DEFAULT_PRESETS = PRESET_ORDER.filter((p) => p !== 'custom') as Preset[]

export default function BatchReportPanel({ terms, opts, configs }: {
  terms: NoteTerms | null
  opts: RunOpts
  configs: ConfigMeta[]
}) {
  const { t, lang } = useI18n()
  const toast = useToast()
  const lab = (en: string, es: string) => (lang === 'es' ? es : en)

  const folder = useLocalFolder('config')
  const [rows, setRows] = useState<Row[]>([])
  const [addSel, setAddSel] = useState('')
  const [defPreset, setDefPreset] = useState<Preset>('client')
  const [defLang, setDefLang] = useState<Lang>(lang as Lang)
  const [defPhotos, setDefPhotos] = useState<PhotoMode>('auto')

  // Global branding for the whole batch (one firm config across every report).
  const [brand, setBrand] = useState<Branding | null>(null)
  const [brandName, setBrandName] = useState<string | null>(null)
  const [brandPresets, setBrandPresets] = useState<{ file: string; firm_name: string }[]>([])
  const brandFolder = useLocalFolder('branding')

  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)

  useEffect(() => { api.brandingList().then(setBrandPresets).catch(() => {}) }, [])

  const presetOpts = DEFAULT_PRESETS.map((p) => ({ value: p, label: t(`rep_preset_${p}`) }))
  const langOpts: { value: Lang; label: string }[] = [{ value: 'en', label: 'English' }, { value: 'es', label: 'Español' }]
  const photoOpts: { value: PhotoMode; label: string }[] = [
    { value: 'auto', label: lab('Auto photos (matched to sector)', 'Fotos auto (según sector)') },
    { value: 'custom', label: lab('Choose photos…', 'Elegir fotos…') },
    { value: 'none', label: lab('No images', 'Sin imágenes') },
  ]
  const photoSummary = (r: Row) =>
    r.photoMode === 'none' ? lab('No images', 'Sin imágenes')
      : r.photoMode === 'custom' ? lab(`${r.photos.length} photo${r.photos.length === 1 ? '' : 's'}`, `${r.photos.length} foto${r.photos.length === 1 ? '' : 's'}`)
        : lab('Auto photos', 'Fotos auto')

  // Every note the user can add: the current one, the bundled configs, and any
  // JSON in a connected local folder.
  const addOptions = useMemo(() => {
    const out: { value: string; label: string }[] = [{ value: '', label: lab('Add a note…', 'Agregar una nota…') }]
    if (terms) out.push({ value: 'cur', label: `${lab('Current', 'Actual')}: ${terms.name}` })
    for (const c of configs) out.push({ value: `b:${c.file}`, label: c.name })
    for (const f of folder.files) out.push({ value: `l:${f.name}`, label: `${f.name} · ${lab('folder', 'carpeta')}` })
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terms, configs, folder.files, lang])

  const makeRow = (nt: NoteTerms): Row => {
    const keys = keysOf(groupsFor(!!nt.issue_date))
    const p: Preset = defPreset
    return {
      id: ++_rid, terms: nt, sel: new Set(keysForPreset(p, keys)), preset: p,
      lang: defLang, photoMode: defPhotos, photos: [], status: 'idle', expanded: false, selected: false,
    }
  }

  const resolveTerms = async (value: string): Promise<NoteTerms | null> => {
    if (value === 'cur') return terms
    if (value.startsWith('b:')) return api.config(value.slice(2))
    if (value.startsWith('l:')) {
      const f = folder.files.find((x) => x.name === value.slice(2))
      return f ? api.parseConfig(f.raw) : null
    }
    return null
  }

  const addRow = async (value: string) => {
    setAddSel('')
    if (!value) return
    try {
      const nt = await resolveTerms(value)
      if (nt) setRows((r) => [...r, makeRow(nt)])
    } catch {
      toast.push({ title: lab('Could not load that note', 'No se pudo cargar esa nota'), tone: 'red', icon: 'info' })
    }
  }

  const patch = (id: number, p: Partial<Row>) => setRows((r) => r.map((x) => (x.id === id ? { ...x, ...p } : x)))
  const remove = (id: number) => setRows((r) => r.filter((x) => x.id !== id))

  const cloneRow = (r: Row): Row => ({
    ...r, id: ++_rid, sel: new Set(r.sel), photos: [...r.photos], status: 'idle', error: undefined, selected: false,
  })
  const duplicateRow = (id: number) => setRows((r) => {
    const out: Row[] = []
    for (const x of r) { out.push(x); if (x.id === id) out.push(cloneRow(x)) }
    return out
  })

  // Bulk actions over the multi-selected rows.
  const nSelected = rows.filter((r) => r.selected).length
  const duplicateSelected = () => setRows((r) => {
    const out: Row[] = []
    for (const x of r) { out.push(x); if (x.selected) out.push(cloneRow(x)) }
    return out
  })
  const removeSelected = () => setRows((r) => r.filter((x) => !x.selected))
  const toggleSelectAll = () => setRows((r) => { const all = r.every((x) => x.selected); return r.map((x) => ({ ...x, selected: !all })) })

  const applyDefaultsToAll = () => setRows((r) => r.map((x) => {
    const keys = keysOf(groupsFor(!!x.terms.issue_date))
    return { ...x, preset: defPreset, sel: new Set(keysForPreset(defPreset, keys)), lang: defLang, photoMode: defPhotos }
  }))

  // Per-row section editing.
  const rowGroups = (r: Row) => groupsFor(!!r.terms.issue_date)
  const toggleKey = (r: Row, key: string) => patch(r.id, {
    sel: (() => { const n = new Set(r.sel); n.has(key) ? n.delete(key) : n.add(key); return n })(), preset: 'custom',
  })
  const toggleGroup = (r: Row, gkeys: string[]) => patch(r.id, {
    sel: (() => {
      const n = new Set(r.sel); const allOn = gkeys.every((k) => n.has(k))
      gkeys.forEach((k) => (allOn ? n.delete(k) : n.add(k))); return n
    })(), preset: 'custom',
  })
  const applyRowPreset = (r: Row, p: Preset) => {
    if (p === 'custom') { patch(r.id, { preset: 'custom' }); return }
    const keys = keysOf(rowGroups(r))
    patch(r.id, { preset: p, sel: new Set(keysForPreset(p, keys)) })
  }

  // Resolve the matched sector for an auto-mode row's label (lazy, once).
  useEffect(() => {
    for (const r of rows) {
      if (r.expanded && r.photoMode === 'auto' && r.sector === undefined) {
        patch(r.id, { sector: '' })   // mark in-flight so we don't refetch
        resolveSector(r.terms, lang).then((s) => patch(r.id, { sector: s })).catch(() => patch(r.id, { sector: 'markets' }))
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, lang])

  // Branding loading.
  const loadBrandPreset = async (value: string) => {
    if (!value) { setBrand(null); setBrandName(null); return }
    try {
      if (value.startsWith('local:')) {
        const f = brandFolder.files.find((x) => `local:${x.name}` === value)
        if (f) { setBrand(f.raw as Branding); setBrandName(f.name) }
      } else {
        const b = await api.branding(value) as Branding
        setBrand(b); setBrandName((b.firm_name as string) || value)
      }
    } catch { toast.push({ title: lab('Could not load branding', 'No se pudo cargar la marca'), tone: 'red', icon: 'info' }) }
  }
  const onUploadBrand = (file: File | undefined) => {
    if (!file) return
    const r = new FileReader()
    r.onload = () => {
      try { const b = JSON.parse(String(r.result)) as Branding; setBrand(b); setBrandName((b.firm_name as string) || file.name.replace(/\.json$/i, '')) }
      catch { toast.push({ title: lab('Invalid branding file', 'Archivo de marca inválido'), tone: 'red', icon: 'info' }) }
    }
    r.readAsText(file)
  }

  // Per-report branding: the global brand config plus this row's photo pool.
  const brandingFor = (photos: string[]): Branding | null => {
    if (!brand && !photos.length) return null
    return { ...(brand ?? {}), ...(photos.length ? { filler_images_base64: photos } : {}) }
  }

  const generate = async () => {
    if (!rows.length || running) return
    setRunning(true)
    setProgress({ done: 0, total: rows.length })
    setRows((r) => r.map((x) => ({ ...x, status: 'idle', error: undefined })))
    const zip = new JSZip()
    const used = new Set<string>()
    let ok = 0
    try {
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i]
        if (row.sel.size === 0) {                       // empty ⇒ backend would render EVERYTHING; skip instead
          patch(row.id, { status: 'error', error: lab('no sections selected', 'sin secciones') })
          setProgress({ done: i + 1, total: rows.length }); continue
        }
        patch(row.id, { status: 'running', error: undefined })
        try {
          const photos = row.photoMode === 'custom' ? row.photos
            : row.photoMode === 'auto' ? await autoIndustryPhotos(row.terms, row.lang, photoCapacity(row.sel.size))
              : []
          const res = await api.report({
            terms: row.terms, sections: [...row.sel], lang: row.lang, branding: brandingFor(photos),
            n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine,
            compare_terms: null,
            report_kind: row.preset === 'custom' ? null : row.preset,
          })
          const blob = await res.blob()
          let fname = `${safeName(row.terms.name)}.pdf`
          for (let n = 2; used.has(fname); n++) fname = `${safeName(row.terms.name)}_${n}.pdf`
          used.add(fname); zip.file(fname, blob)
          patch(row.id, { status: 'done' }); ok++
        } catch (e) {
          patch(row.id, { status: 'error', error: String(e instanceof Error ? e.message : e) })
        }
        setProgress({ done: i + 1, total: rows.length })
      }
      if (ok === 0) { toast.push({ title: lab('No reports were generated', 'No se generó ningún informe'), tone: 'red', icon: 'info' }); return }
      const out = await zip.generateAsync({ type: 'blob' })
      const date = new Date().toISOString().slice(0, 10)
      const url = URL.createObjectURL(out)
      const a = document.createElement('a'); a.href = url; a.download = `batch_reports_${date}.zip`
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
      const mb = out.size / 1048576
      toast.push({
        title: lab('Batch reports ready', 'Informes en lote listos'),
        sub: `${ok}/${rows.length} · ${mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(out.size / 1024)} KB`}`,
        tone: 'accent', icon: 'check',
      })
    } finally { setRunning(false); setProgress(null) }
  }

  const statusDot = (s: RowStatus) => {
    if (s === 'running') return <Icon name="spinner" size={14} />
    if (s === 'done') return <span style={{ color: 'var(--accent)' }}><Icon name="check" size={14} /></span>
    if (s === 'error') return <span style={{ color: 'var(--red)' }}><Icon name="info" size={14} /></span>
    return <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--border-strong)', display: 'inline-block' }} />
  }
  const iconBtn = (onClick: () => void, name: 'plus' | 'x', title: string, disabled = false) => (
    <button onClick={onClick} disabled={disabled} aria-label={title} title={title} className="lift"
            style={{ flexShrink: 0, width: 30, height: 30, borderRadius: 8, border: '1px solid var(--border)',
                     background: 'var(--surface-2)', color: 'var(--text-muted)', cursor: disabled ? 'default' : 'pointer',
                     display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Icon name={name} size={13} />
    </button>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} className="fade-up">
      <Panel title={lab('Batch reports', 'Informes en lote')}
             right={lab('One ZIP, one PDF per note', 'Un ZIP, un PDF por nota')}>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
          {lab('Add notes, then tune each report independently — audience preset, exact sections, language and images — and generate them all in one pass as a single ZIP. Expand a row for the full options; duplicate a row to make variants of the same note.',
               'Agrega notas y ajusta cada informe por separado — preset, secciones exactas, idioma e imágenes — y genéralos todos de una vez en un solo ZIP. Expande una fila para ver todas las opciones; duplica una fila para crear variantes de la misma nota.')}
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ minWidth: 260, flex: 1 }}>
            <Select value={addSel} onChange={(v) => addRow(v)} ariaLabel={lab('Add a note', 'Agregar una nota')} options={addOptions} />
          </div>
          {folder.supported && !folder.folder && <FolderConnect fld={folder} />}
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{lab('New-row defaults', 'Predeterminados')}:</span>
          <div style={{ minWidth: 150 }}><Select value={defPreset} onChange={setDefPreset} options={presetOpts} ariaLabel={lab('Default preset', 'Preset predeterminado')} /></div>
          <div style={{ minWidth: 120 }}><Select value={defLang} onChange={setDefLang} options={langOpts} ariaLabel={lab('Default language', 'Idioma predeterminado')} /></div>
          <div style={{ minWidth: 190 }}><Select value={defPhotos} onChange={setDefPhotos} options={photoOpts} ariaLabel={lab('Default images', 'Imágenes predeterminadas')} /></div>
          {rows.length > 0 && (
            <button className="btn btn--ghost" style={{ padding: '6px 11px' }} onClick={applyDefaultsToAll} disabled={running}>
              {lab('Apply to all', 'Aplicar a todas')}
            </button>
          )}
        </div>
      </Panel>

      {/* Global branding for the batch */}
      <Panel title={lab('Branding', 'Marca')} right={brandName ? undefined : lab('optional', 'opcional')}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ minWidth: 220 }}>
            <Select value="" placeholder={lab('Load a brand config…', 'Cargar configuración de marca…')} ariaLabel={lab('Branding preset', 'Preset de marca')}
                    onChange={(v) => loadBrandPreset(v)}
                    options={[
                      ...brandFolder.files.map((f) => ({ value: `local:${f.name}`, label: `${f.name} · ${lab('folder', 'carpeta')}` })),
                      ...brandPresets.map((p) => ({ value: p.file, label: p.firm_name })),
                    ]} />
          </div>
          <label className="btn" style={{ padding: '7px 12px', cursor: 'pointer' }}>
            <Icon name="upload" size={13} /> {lab('Upload config', 'Subir configuración')}
            <input type="file" accept="application/json,.json" style={{ display: 'none' }}
                   onChange={(e) => { onUploadBrand(e.target.files?.[0]); e.currentTarget.value = '' }} />
          </label>
          {brandFolder.supported && !brandFolder.folder && <FolderConnect fld={brandFolder} />}
          {brandName && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              <span style={{ color: 'var(--accent)' }}><Icon name="check" size={13} /></span>
              {lab('Using', 'Usando')} <strong style={{ color: 'var(--text)' }}>{brandName}</strong>
              <button className="btn btn--ghost" style={{ padding: '3px 8px', fontSize: 11 }} onClick={() => { setBrand(null); setBrandName(null) }}>
                {lab('Clear', 'Quitar')}
              </button>
            </span>
          )}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 8, lineHeight: 1.5 }}>
          {lab('Applied to every report in the batch (colours, logos, fonts, cover/disclaimer). Each report renders it in its own language.',
               'Se aplica a todos los informes del lote (colores, logos, fuentes, portada/aviso). Cada informe la renderiza en su propio idioma.')}
        </div>
      </Panel>

      {/* Rows */}
      {rows.length === 0 ? (
        <Panel>
          <div style={{ textAlign: 'center', padding: '26px 12px', color: 'var(--text-faint)', fontSize: 13 }}>
            {lab('No notes added yet. Pick one above to start your batch.', 'Aún no hay notas. Elige una arriba para comenzar tu lote.')}
          </div>
        </Panel>
      ) : (
        <Panel pad={0}>
          {/* bulk toolbar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 18px', borderBottom: '1px solid var(--border)' }}>
            <button onClick={toggleSelectAll} disabled={running} className="btn btn--ghost" style={{ padding: '5px 10px', fontSize: 12 }}>
              {rows.every((r) => r.selected) ? lab('Deselect all', 'Deseleccionar todo') : lab('Select all', 'Seleccionar todo')}
            </button>
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{rows.length} {lab(rows.length === 1 ? 'note' : 'notes', rows.length === 1 ? 'nota' : 'notas')}</span>
            {nSelected > 0 && (
              <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
                <button onClick={duplicateSelected} disabled={running} className="btn btn--ghost" style={{ padding: '5px 10px', fontSize: 12 }}>
                  <Icon name="plus" size={12} /> {lab(`Duplicate ${nSelected}`, `Duplicar ${nSelected}`)}
                </button>
                <button onClick={removeSelected} disabled={running} className="btn btn--ghost" style={{ padding: '5px 10px', fontSize: 12, color: 'var(--red)' }}>
                  <Icon name="x" size={12} /> {lab(`Remove ${nSelected}`, `Quitar ${nSelected}`)}
                </button>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {rows.map((row, i) => (
              <div key={row.id} style={{ borderTop: i === 0 ? 'none' : '1px solid var(--border)' }}>
                {/* summary row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '12px 18px' }}>
                  <input type="checkbox" checked={row.selected} disabled={running}
                         onChange={(e) => patch(row.id, { selected: e.target.checked })}
                         style={{ width: 15, height: 15, accentColor: 'var(--accent)', flexShrink: 0, cursor: 'pointer' }} />
                  <div style={{ width: 16, textAlign: 'center', flexShrink: 0 }}>{statusDot(row.status)}</div>
                  <button onClick={() => patch(row.id, { expanded: !row.expanded })}
                          style={{ flex: 1, minWidth: 0, textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ transition: 'transform .15s', transform: row.expanded ? 'rotate(90deg)' : 'none', color: 'var(--text-faint)', flexShrink: 0 }}>›</span>
                    <span style={{ minWidth: 0 }}>
                      <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.terms.name}</span>
                      <span style={{ display: 'block', fontSize: 11, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {t(`rep_preset_${row.preset}`)} · {row.lang.toUpperCase()} · {photoSummary(row)}
                        {row.status === 'error' && row.error ? ` — ${row.error}` : ''}
                      </span>
                    </span>
                  </button>
                  {iconBtn(() => duplicateRow(row.id), 'plus', lab('Duplicate', 'Duplicar'), running)}
                  {iconBtn(() => remove(row.id), 'x', lab('Remove', 'Quitar'), running)}
                </div>

                {/* expanded editor */}
                {row.expanded && (
                  <div style={{ padding: '4px 18px 20px 45px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                    <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{lab('Language', 'Idioma')}</span>
                      <div style={{ minWidth: 120 }}><Select value={row.lang} onChange={(v) => patch(row.id, { lang: v })} options={langOpts} ariaLabel={lab('Language', 'Idioma')} /></div>
                      <span style={{ fontSize: 11.5, color: 'var(--text-faint)', marginLeft: 8 }}>{lab('Images', 'Imágenes')}</span>
                      <div style={{ minWidth: 200 }}><Select value={row.photoMode} onChange={(v) => patch(row.id, { photoMode: v })} options={photoOpts} ariaLabel={lab('Images', 'Imágenes')} /></div>
                    </div>

                    {/* preset pills */}
                    <div>
                      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>{t('rep_preset')}</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {PRESET_ORDER.map((p) => (
                          <button key={p} type="button" className="preset-pill" data-on={row.preset === p}
                                  title={t(`rep_preset_${p}_desc`)} onClick={() => applyRowPreset(row, p)}>
                            {t(`rep_preset_${p}`)}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* section tree */}
                    <SectionTree groups={rowGroups(row)} sel={row.sel} lang={lang}
                                 onToggle={(k) => toggleKey(row, k)} onToggleGroup={(g) => toggleGroup(row, g.items.map((it) => it[0]))} />

                    {/* images */}
                    {row.photoMode === 'custom' && (
                      <CoverPhotoPicker terms={row.terms} selected={row.photos} max={photoCapacity(row.sel.size)}
                                        onChange={(urls) => patch(row.id, { photos: urls })} />
                    )}
                    {row.photoMode === 'auto' && (
                      <div style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.5 }}>
                        {row.sector
                          ? lab(`Sector-matched photos will be pulled for “${t(`sector_${row.sector}`)}”, cover + back + filler.`,
                                `Se buscarán fotos del sector “${t(`sector_${row.sector}`)}”, portada + contraportada + relleno.`)
                          : lab('Detecting the underlyings’ sector…', 'Detectando el sector de los subyacentes…')}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Generate */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button className="btn btn--primary" onClick={generate} disabled={!rows.length || running} style={{ padding: '10px 18px' }}>
          {running
            ? (progress ? lab(`Generating ${progress.done} / ${progress.total}…`, `Generando ${progress.done} / ${progress.total}…`) : lab('Generating…', 'Generando…'))
            : <><Icon name="chart" size={14} /> {lab(`Generate ${rows.length} report${rows.length === 1 ? '' : 's'} (ZIP)`, `Generar ${rows.length} informe${rows.length === 1 ? '' : 's'} (ZIP)`)}</>}
        </button>
        {running && progress && (
          <div style={{ flex: 1, minWidth: 160, height: 6, borderRadius: 4, background: 'var(--surface-2)', overflow: 'hidden' }}>
            <div style={{ width: `${(progress.done / progress.total) * 100}%`, height: '100%', background: 'var(--accent)', transition: 'width .3s ease' }} />
          </div>
        )}
      </div>
    </div>
  )
}
