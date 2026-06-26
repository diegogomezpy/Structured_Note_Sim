import { useRef, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { pct } from '../lib/format'
import { nObs } from '../lib/terms'
import Icon from './Icon'
import { Slider, SelectField, SegmentedField, ToggleField, Select } from './fields'
import AddNoteHelp from './AddNoteHelp'
import UnderlyingPicker from './UnderlyingPicker'
import FolderConnect from './FolderConnect'
import { useLocalFolder } from '../lib/localFolder'
import { useToast } from './Toast'
import type { ConfigMeta, NoteTerms } from '../api/types'

export interface RunOpts {
  n_paths: number
  engine: 'numpy' | 'cpp'
  seed: number
  calib_years: number
}

const FREQS: NoteTerms['payment_freq'][] = ['monthly', 'quarterly', 'semi-annual', 'annual']
/** Compact codes for the narrow rail's segmented frequency control. */
const FREQ_SHORT: Record<NoteTerms['payment_freq'], string> = {
  monthly: 'M', quarterly: 'Q', 'semi-annual': 'S/A', annual: 'A',
}
const BASKETS: NoteTerms['coupon_basket'][] = ['worst_of', 'best_of', 'average']
const pct0 = (v: number) => pct(v, 0)

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
  const set = <K extends keyof NoteTerms>(k: K, v: NoteTerms[K]) => onChange({ ...terms, [k]: v })
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

  const downloadConfig = () => {
    const blob = new Blob([JSON.stringify(terms, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const safe = (terms.name || 'note').replace(/[^A-Za-z0-9_.-]+/g, '_').slice(0, 60)
    a.href = url; a.download = `${safe || 'note'}.json`
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
  }

  // Save the current note straight back into the connected folder — overwriting
  // the file it was loaded from, or creating one named after the note. No
  // download / re-import round-trip: the website edits the config in place.
  const saveToFolder = async () => {
    setSaving(true)
    try {
      const saved = await local.save(activeLocalName ?? (terms.name || 'note'), terms)
      setLocalSel(`local:${saved}`)
      toast.push({ title: t('cfg_saved'), sub: `${saved}.json · ${local.folder}`, tone: 'accent', icon: 'check' })
    } catch {
      toast.push({ title: t('cfg_save_failed'), sub: t('cfg_save_failed_sub'), tone: 'red', icon: 'info' })
    } finally { setSaving(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div data-tour="term-sheet">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('config_label')}</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <AddNoteHelp />
            {local.canSave && (
              <button className="btn btn--ghost" style={{ padding: '3px 7px' }} disabled={saving}
                      onClick={saveToFolder}
                      title={activeLocalName ? t('cfg_save_over_hint', { name: activeLocalName }) : t('cfg_save_to_folder_hint')}
                      aria-label={t('cfg_save_to_folder')}>
                <Icon name={saving ? 'spinner' : 'save'} size={14} />
              </button>
            )}
            <button className="btn btn--ghost" style={{ padding: '3px 7px' }}
                    onClick={downloadConfig} title={t('download_config_hint')} aria-label={t('download_config')}>
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
        {uploadErr && <div style={{ fontSize: 11.5, color: 'var(--red)', marginTop: 5 }}>{uploadErr}</div>}
      </div>

      <div data-tour="underlyings">
        <UnderlyingPicker tickers={terms.tickers} onChange={(tk) => set('tickers', tk)} />
      </div>

      {/* Inline editor for the terms that drive the note diagram above. The full
          settings overlay still holds the rarer fields (engine, ratings, capital
          guarantee, upside cap, …). */}
      <div data-tour="terms" style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12 }}>{t('quick_edit')}</div>

        <Slider label={t('maturity')} value={terms.maturity} min={0.25} max={5} step={0.25} tip={t('tip_maturity')}
                editSuffix="y" fmt={(v) => `${v.toFixed(2)} y`} onChange={(v) => set('maturity', v)} />
        <SegmentedField label={t('frequency')} value={terms.payment_freq} tip={t('tip_frequency')}
                        options={FREQS.map((f) => ({ value: f, label: FREQ_SHORT[f] }))}
                        onChange={(v) => set('payment_freq', v)} />
        <Slider label={t('coupon_pa')} value={terms.coupon_pa} min={0} max={0.3} step={0.005} tip={t('tip_coupon_pa')}
                pct editSuffix="%" fmt={(v) => pct(v, 1)} onChange={(v) => set('coupon_pa', v)} />

        <Slider label={t('coupon_barrier')} value={terms.coupon_barrier} min={0} max={1} step={0.01} tip={t('tip_coupon_barrier')}
                pct editSuffix="%" fmt={pct0} onChange={(v) => set('coupon_barrier', v)} />
        <Slider label={t('knock_in_barrier')} value={terms.knock_in_barrier} min={0} max={1} step={0.01} tip={t('tip_knock_in')}
                tone="danger" pct editSuffix="%" fmt={pct0} onChange={(v) => set('knock_in_barrier', v)} />
        <Slider label={t('autocall_barrier')} value={terms.autocall_barrier} min={0.5} max={1.5} step={0.01} tip={t('tip_autocall')}
                pct editSuffix="%" fmt={pct0} onChange={(v) => set('autocall_barrier', v)} />
      </div>

      {/* Second group — the next-most-edited mechanics, inline so they don't
          require the settings overlay. */}
      <div data-tour="mechanics" style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12 }}>{t('quick_mechanics')}</div>

        <Slider label={t('autocall_start')} value={Math.min(terms.autocall_start_period, nObs(terms))}
                min={1} max={Math.max(1, nObs(terms))} step={1} fmt={(v) => `P${v}`}
                editInt editPrefix="P" editClamp={[1, Math.max(1, nObs(terms))]}
                onChange={(v) => set('autocall_start_period', v)} />
        <SelectField label={t('coupon_basket')} value={terms.coupon_basket}
                     options={BASKETS.map((b) => ({ value: b, label: t(`basket_${b}`) }))}
                     onChange={(v) => set('coupon_basket', v)} />
        <SelectField label={t('autocall_basket')} value={terms.autocall_basket}
                     options={BASKETS.map((b) => ({ value: b, label: t(`basket_${b}`) }))}
                     onChange={(v) => set('autocall_basket', v)} />
        <ToggleField label={t('memory')} checked={terms.memory} onChange={(v) => set('memory', v)} />
        <ToggleField label={t('one_star')} checked={terms.one_star_level != null}
                     onChange={(on) => set('one_star_level', on ? 1.0 : null)} />
        {terms.one_star_level != null && (
          <Slider label={t('one_star_level')} value={terms.one_star_level} min={0.5} max={1.5} step={0.01}
                  pct editSuffix="%" fmt={pct0} onChange={(v) => set('one_star_level', v)} />
        )}
      </div>

      <button data-tour="settings" className="btn" style={{ justifyContent: 'center', padding: '10px' }} onClick={onOpenSettings}>
        <Icon name="chart" size={15} /> {t('edit_settings')}
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
