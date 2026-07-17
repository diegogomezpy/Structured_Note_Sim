import { useRef, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import { SegmentedField, Select } from './fields'
import AddNoteHelp from './AddNoteHelp'
import UnderlyingPicker from './UnderlyingPicker'
import FolderConnect from './FolderConnect'
import { useLocalFolder, safeName } from '../lib/localFolder'
import { useToast } from './Toast'
import { detectNoteType, applyPreset, NOTE_TYPES, type NoteType } from '../lib/noteType'
import type { ConfigMeta, NoteTerms } from '../api/types'

export interface RunOpts {
  n_paths: number
  engine: 'numpy' | 'cpp'
  seed: number
  calib_years: number
}

export default function SetupRail({
  terms, onChange, configs, configFile, onSelectConfig, onUploadConfig, running, stale, onRun, onOpenSettings,
}: {
  terms: NoteTerms
  onChange: (t: NoteTerms) => void
  configs: ConfigMeta[]
  configFile: string
  onSelectConfig: (file: string) => void
  onUploadConfig: (raw: unknown) => void
  opts: RunOpts
  running: boolean
  stale: boolean
  onRun: () => void
  onOpenSettings: () => void
}) {
  const { t } = useI18n()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploadErr, setUploadErr] = useState('')
  const [saving, setSaving] = useState(false)

  // The user's own folder of note-config JSONs (auto-detected via the File System
  // Access API), shown alongside the examples bundled in the repo. `localSel`
  // tracks a chosen local config so the selector keeps showing its name (a local
  // load routes through onUploadConfig, which clears the repo `configFile`).
  const local = useLocalFolder('note-configs')
  const [localSel, setLocalSel] = useState<string | null>(null)
  const activeLocalName = localSel?.startsWith('local:') ? localSel.slice('local:'.length) : null

  const onFile = async (file: File | undefined) => {
    setUploadErr('')
    if (!file) return
    try {
      onUploadConfig(JSON.parse(await file.text()))
    } catch {
      setUploadErr(t('upload_invalid'))
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  const downloadConfig = async () => {
    // When a writable folder is connected, "download" writes the config straight
    // into that folder (named after the note) rather than the browser Downloads
    // dir — so downloaded configs land where the app auto-detects them. Falls back
    // to a browser download when no folder is connected (or the write is denied).
    if (local.canSave) {
      try {
        const saved = await local.save(terms.name || 'note', terms)
        setLocalSel(`local:${saved}`)
        toast.push({ title: t('cfg_saved'), sub: `${saved}.json · ${local.folder}`, tone: 'accent', icon: 'check' })
        return
      } catch { /* fall through to a browser download */ }
    }
    const blob = new Blob([JSON.stringify(terms, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const safe = (terms.name || 'note').replace(/[^A-Za-z0-9_.-]+/g, '_').slice(0, 60)
    a.href = url; a.download = `${safe || 'note'}.json`
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
  }

  // Save the current note straight back into the connected folder. The file is
  // named after the note (`terms.name`), so renaming the note renames the file:
  // we pass the file it was loaded from as `removeOld` and the writer deletes it
  // once the new name is written. A brand-new note (no loaded file) just creates
  // one. No download / re-import round-trip: the website edits the config in place.
  const targetBase = safeName(activeLocalName ? (terms.name || activeLocalName) : (terms.name || 'note'))
  const saveToFolder = async () => {
    setSaving(true)
    try {
      const saved = await local.save(terms.name || activeLocalName || 'note', terms, activeLocalName)
      setLocalSel(`local:${saved}`)
      const renamed = activeLocalName && saved !== activeLocalName
      toast.push({
        title: renamed ? t('cfg_renamed') : t('cfg_saved'),
        sub: renamed ? `${activeLocalName}.json → ${saved}.json · ${local.folder}` : `${saved}.json · ${local.folder}`,
        tone: 'accent', icon: 'check',
      })
    } catch {
      toast.push({ title: t('cfg_save_failed'), sub: t('cfg_save_failed_sub'), tone: 'red', icon: 'info' })
    } finally { setSaving(false) }
  }

  // The rail is deliberately minimal — which note, on what, of what type. Every
  // term/mechanic knob lives in the settings overlay.
  const noteType = detectNoteType(terms)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div data-tour="term-sheet">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('config_label')}</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <AddNoteHelp />
            <button className="btn btn--ghost" style={{ padding: '3px 7px' }}
                    onClick={downloadConfig}
                    title={local.canSave ? t('download_to_folder_hint') : t('download_config_hint')}
                    aria-label={t('download_config')}>
              <Icon name="download" size={14} />
            </button>
            <button className="btn btn--ghost" style={{ padding: '3px 7px' }}
                    onClick={() => fileRef.current?.click()} title={t('upload_config_hint')} aria-label={t('upload_config')}>
              <Icon name="upload" size={14} />
            </button>
          </div>
          <input ref={fileRef} type="file" accept="application/json,.json" style={{ display: 'none' }}
                 onChange={(e) => onFile(e.target.files?.[0])} />
        </div>
        <Select value={localSel ?? configFile} ariaLabel={t('config_label')}
                options={[
                  { value: '', label: t('blank_note') },
                  ...local.files.map((f) => ({ value: `local:${f.name}`, label: `${f.name} ${t('folder_tag')}` })),
                  ...configs.map((c) => ({ value: c.file, label: c.name })),
                ]}
                onChange={(v) => {
                  if (v.startsWith('local:')) {
                    const f = local.files.find((f) => `local:${f.name}` === v)
                    if (f) { setLocalSel(v); onUploadConfig(f.raw) }
                  } else { setLocalSel(null); onSelectConfig(v) }
                }} />
        <FolderConnect fld={local} />
        {/* Clear, labelled save-back action — overwrites the loaded folder file
            in place, or creates a new one when the note didn't come from the
            folder. Only shown once a writable folder is connected. */}
        {local.canSave && (
          <>
            <button className="btn" style={{ marginTop: 8, width: '100%', justifyContent: 'center',
                                             maxWidth: '100%', overflow: 'hidden' }}
                    disabled={saving} onClick={saveToFolder}
                    title={activeLocalName ? `${targetBase}.json` : undefined}>
              <Icon name={saving ? 'spinner' : 'save'} size={14} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
                {activeLocalName ? t('cfg_save_changes', { name: targetBase }) : t('cfg_save_new_file')}
              </span>
            </button>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 5 }}>{t('folder_save_hint')}</div>
          </>
        )}
        {uploadErr && <div style={{ fontSize: 11.5, color: 'var(--red)', marginTop: 5 }}>{uploadErr}</div>}
      </div>

      <div data-tour="underlyings">
        <UnderlyingPicker tickers={terms.tickers} onChange={(tk) => onChange({ ...terms, tickers: tk })} />
      </div>

      {/* Note-type toggle — switch structure families without opening the overlay.
          Everything below it (maturity, barriers, coupons, participation styles,
          mechanics) lives in the settings overlay: the rail stays a short
          identity strip — which note, on what, of what type — so the freed space
          can carry the navigation menu instead. */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <SegmentedField label={t('sec_note_type')} tip={t('tip_note_type')} value={noteType}
                        options={NOTE_TYPES.map((nt) => ({ value: nt, label: t(`nt_${nt}`) }))}
                        onChange={(v) => onChange(applyPreset(terms, v as NoteType))} />
      </div>

      <button data-tour="settings" className="btn" style={{ justifyContent: 'center', padding: '10px' }} onClick={onOpenSettings}>
        <Icon name="chart" size={15} /> {t('edit_terms_full')}
      </button>

      <button data-tour="run" className={`btn btn--primary${stale && !running ? ' btn--pulse' : ''}`}
              style={{ justifyContent: 'center', padding: '12px', fontSize: 14 }}
              disabled={running} onClick={onRun}>
        <Icon name={running ? 'spinner' : stale ? 'refresh' : 'play'} size={16} />
        {running ? t('running') : stale ? t('rerun') : t('run')}
      </button>
    </div>
  )
}
