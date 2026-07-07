import { useMemo, useState } from 'react'
import JSZip from 'jszip'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { useToast } from './Toast'
import Panel from './Panel'
import Icon from './Icon'
import { Select } from './fields'
import FolderConnect from './FolderConnect'
import { useLocalFolder, safeName } from '../lib/localFolder'
import { SCOPE_KEYS, autoIndustryPhotos, type BatchScope, type PhotoMode } from '../lib/batchReport'
import type { ConfigMeta, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'

type RowStatus = 'idle' | 'running' | 'done' | 'error'
interface Row {
  id: number
  terms: NoteTerms
  scope: BatchScope
  photos: PhotoMode
  status: RowStatus
  error?: string
}

let _rid = 0

export default function BatchReportPanel({ terms, opts, configs }: {
  terms: NoteTerms | null
  opts: RunOpts
  configs: ConfigMeta[]
}) {
  const { lang } = useI18n()
  const toast = useToast()
  const lab = (en: string, es: string) => (lang === 'es' ? es : en)

  const folder = useLocalFolder('config')
  const [rows, setRows] = useState<Row[]>([])
  const [addSel, setAddSel] = useState('')
  const [defScope, setDefScope] = useState<BatchScope>('details_mc')
  const [defPhotos, setDefPhotos] = useState<PhotoMode>('auto')
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)

  const scopeOpts: { value: BatchScope; label: string }[] = [
    { value: 'details', label: lab('Note details only', 'Solo detalle de la nota') },
    { value: 'details_mc', label: lab('Details + Monte Carlo', 'Detalle + Monte Carlo') },
    { value: 'full', label: lab('Full report', 'Informe completo') },
  ]
  const photoOpts: { value: PhotoMode; label: string }[] = [
    { value: 'auto', label: lab('Auto industry photos', 'Fotos por industria (auto)') },
    { value: 'none', label: lab('No images', 'Sin imágenes') },
  ]

  // Every note the user can add: the current one, the bundled configs, and any
  // JSON in a connected local folder. Value encodes the source so we resolve the
  // right NoteTerms on add.
  const addOptions = useMemo(() => {
    const out: { value: string; label: string }[] = [{ value: '', label: lab('Add a note…', 'Agregar una nota…') }]
    if (terms) out.push({ value: 'cur', label: `${lab('Current', 'Actual')}: ${terms.name}` })
    for (const c of configs) out.push({ value: `b:${c.file}`, label: c.name })
    for (const f of folder.files) out.push({ value: `l:${f.name}`, label: `${f.name} · ${lab('folder', 'carpeta')}` })
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terms, configs, folder.files, lang])

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
      if (!nt) return
      setRows((r) => [...r, { id: ++_rid, terms: nt, scope: defScope, photos: defPhotos, status: 'idle' }])
    } catch {
      toast.push({ title: lab('Could not load that note', 'No se pudo cargar esa nota'), tone: 'red', icon: 'info' })
    }
  }

  const patch = (id: number, p: Partial<Row>) => setRows((r) => r.map((x) => (x.id === id ? { ...x, ...p } : x)))
  const remove = (id: number) => setRows((r) => r.filter((x) => x.id !== id))
  const applyToAll = () => setRows((r) => r.map((x) => ({ ...x, scope: defScope, photos: defPhotos })))

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
        patch(row.id, { status: 'running', error: undefined })
        try {
          const branding = row.photos === 'auto'
            ? { filler_images_base64: await autoIndustryPhotos(row.terms, lang, row.scope) }
            : null
          const res = await api.report({
            terms: row.terms,
            sections: SCOPE_KEYS[row.scope],
            lang,
            branding: branding && branding.filler_images_base64.length ? branding : null,
            n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine,
            compare_terms: null,
          })
          const blob = await res.blob()
          // Unique filename inside the zip (two notes can share a name).
          let fname = `${safeName(row.terms.name)}.pdf`
          for (let n = 2; used.has(fname); n++) fname = `${safeName(row.terms.name)}_${n}.pdf`
          used.add(fname)
          zip.file(fname, blob)
          patch(row.id, { status: 'done' })
          ok++
        } catch (e) {
          patch(row.id, { status: 'error', error: String(e instanceof Error ? e.message : e) })
        }
        setProgress({ done: i + 1, total: rows.length })
      }
      if (ok === 0) {
        toast.push({ title: lab('No reports were generated', 'No se generó ningún informe'), tone: 'red', icon: 'info' })
        return
      }
      const out = await zip.generateAsync({ type: 'blob' })
      const date = new Date().toISOString().slice(0, 10)
      const url = URL.createObjectURL(out)
      const a = document.createElement('a')
      a.href = url; a.download = `batch_reports_${date}.zip`
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
      const mb = out.size / 1048576
      toast.push({
        title: lab('Batch reports ready', 'Informes en lote listos'),
        sub: `${ok}/${rows.length} · ${mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(out.size / 1024)} KB`}`,
        tone: 'accent', icon: 'check',
      })
    } finally {
      setRunning(false)
      setProgress(null)
    }
  }

  const statusDot = (s: RowStatus) => {
    if (s === 'running') return <Icon name="spinner" size={14} />
    if (s === 'done') return <span style={{ color: 'var(--accent)' }}><Icon name="check" size={14} /></span>
    if (s === 'error') return <span style={{ color: 'var(--red)' }}><Icon name="info" size={14} /></span>
    return <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--border-strong)', display: 'inline-block' }} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} className="fade-up">
      <Panel title={lab('Batch reports', 'Informes en lote')}
             right={lab('One ZIP, one PDF per note', 'Un ZIP, un PDF por nota')}>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
          {lab('Add several notes, choose a report scope and image style for each, then generate every report in one pass — downloaded as a single ZIP. Notes are rendered one at a time without loading each on the dashboard.',
               'Agrega varias notas, elige el alcance del informe y el estilo de imagen para cada una, y genera todos los informes de una vez, descargados como un solo ZIP. Las notas se procesan una por una sin cargarlas en el panel.')}
        </div>

        {/* Add a note */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ minWidth: 260, flex: 1 }}>
            <Select value={addSel} onChange={(v) => addRow(v)} ariaLabel={lab('Add a note', 'Agregar una nota')}
                    options={addOptions} />
          </div>
          {folder.supported && !folder.folder && (
            <FolderConnect fld={folder} />
          )}
        </div>

        {/* Defaults applied to new rows */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{lab('Defaults', 'Predeterminados')}:</span>
          <div style={{ minWidth: 190 }}>
            <Select value={defScope} onChange={setDefScope} options={scopeOpts} ariaLabel={lab('Default scope', 'Alcance predeterminado')} />
          </div>
          <div style={{ minWidth: 190 }}>
            <Select value={defPhotos} onChange={setDefPhotos} options={photoOpts} ariaLabel={lab('Default images', 'Imágenes predeterminadas')} />
          </div>
          {rows.length > 0 && (
            <button className="btn btn--ghost" style={{ padding: '6px 11px' }} onClick={applyToAll} disabled={running}>
              {lab('Apply to all', 'Aplicar a todas')}
            </button>
          )}
        </div>
      </Panel>

      {/* Row list */}
      {rows.length === 0 ? (
        <Panel>
          <div style={{ textAlign: 'center', padding: '26px 12px', color: 'var(--text-faint)', fontSize: 13 }}>
            {lab('No notes added yet. Pick one above to start your batch.', 'Aún no hay notas. Elige una arriba para comenzar tu lote.')}
          </div>
        </Panel>
      ) : (
        <Panel pad={0}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {rows.map((row, i) => (
              <div key={row.id} style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '13px 18px',
                borderTop: i === 0 ? 'none' : '1px solid var(--border)',
              }}>
                <div style={{ width: 18, textAlign: 'center', flexShrink: 0 }}>{statusDot(row.status)}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.terms.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {Object.keys(row.terms.tickers ?? {}).join(' · ')}
                    {row.status === 'error' && row.error ? ` — ${row.error}` : ''}
                  </div>
                </div>
                <div style={{ width: 180, flexShrink: 0 }}>
                  <Select value={row.scope} onChange={(v) => patch(row.id, { scope: v })} options={scopeOpts} ariaLabel={lab('Scope', 'Alcance')} />
                </div>
                <div style={{ width: 190, flexShrink: 0 }}>
                  <Select value={row.photos} onChange={(v) => patch(row.id, { photos: v })} options={photoOpts} ariaLabel={lab('Images', 'Imágenes')} />
                </div>
                <button onClick={() => remove(row.id)} disabled={running} aria-label={lab('Remove', 'Quitar')}
                        className="lift" style={{
                          flexShrink: 0, width: 30, height: 30, borderRadius: 8, border: '1px solid var(--border)',
                          background: 'var(--surface-2)', color: 'var(--text-muted)', cursor: running ? 'default' : 'pointer',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                  <Icon name="x" size={13} />
                </button>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Generate */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button className="btn btn--primary" onClick={generate} disabled={!rows.length || running}
                style={{ padding: '10px 18px' }}>
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
