import { useRef, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { nObs } from '../lib/terms'
import Icon from './Icon'
import { NumField, SelectField, SegmentedField, ToggleField, Select } from './fields'
import AddNoteHelp from './AddNoteHelp'
import UnderlyingPicker from './UnderlyingPicker'
import FolderConnect from './FolderConnect'
import { useLocalFolder, safeName } from '../lib/localFolder'
import { useToast } from './Toast'
import { detectNoteType, applyPreset, NOTE_TYPES, type NoteType } from '../lib/noteType'
import { withDownside, withUpside } from '../lib/participation'
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

/** Small uppercase sub-group header, so downside / upside / cliquet fields read as
    distinct groups in the rail. */
function SubHead({ children }: { children: string }) {
  return <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)', margin: '2px 0 8px' }}>{children}</div>
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

  // The rail is deliberately simple: for a Participation note it shows only the
  // headline knobs (protection + rate + downside style); the full option set
  // lives in the settings overlay.
  const noteType = detectNoteType(terms)
  const isPart = noteType === 'participation'
  const periodic = terms.participation_periodic ?? false
  const pu = terms.participation_upside ?? 'linear'
  const downsideOpts = (['full', 'buffer', 'airbag', 'bear'] as const).map((v) => ({ value: v, label: t(`pd_${v}`) }))
  const upsideOpts = (['linear', 'shark_fin', 'digital'] as const).map((v) => ({ value: v, label: t(`pu_${v}`) }))

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
        <UnderlyingPicker tickers={terms.tickers} onChange={(tk) => set('tickers', tk)} />
      </div>

      {/* Note-type toggle — switch structure families without opening the overlay. */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <SegmentedField label={t('sec_note_type')} value={noteType}
                        options={NOTE_TYPES.map((nt) => ({ value: nt, label: t(`nt_${nt}`) }))}
                        onChange={(v) => onChange(applyPreset(terms, v as NoteType))} />
      </div>

      {/* Inline editor for the terms that drive the note diagram above. The full
          settings overlay still holds the rarer fields (engine, ratings, …). */}
      <div data-tour="terms" style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12 }}>{t('quick_edit')}</div>

        <NumField label={t('maturity')} value={terms.maturity} suffix="y" min={0.25} tip={t('tip_maturity')}
                  onChange={(v) => set('maturity', v)} />
        {isPart ? (<>
          <ToggleField label={t('part_periodic')} tip={t('part_periodic_h')} checked={periodic}
                       onChange={(v) => set('participation_periodic', v)} />
          {periodic && (<>
            <SubHead>{t('grp_cliquet')}</SubHead>
            <SegmentedField label={t('part_reset')} tip={t('tip_part_reset')} value={terms.payment_freq}
                            options={FREQS.map((f) => ({ value: f, label: FREQ_SHORT[f] }))}
                            onChange={(v) => set('payment_freq', v)} />
            <ToggleField label={t('cap_period')} tip={t('tip_cap_period')} checked={terms.period_cap != null}
                         onChange={(on) => set('period_cap', on ? 0.08 : null)} />
            {terms.period_cap != null && (
              <NumField label={t('period_cap')} tip={t('tip_period_cap')} value={terms.period_cap} pct suffix="%"
                        onChange={(v) => set('period_cap', v)} />
            )}
          </>)}
          <SubHead>{t('grp_downside')}</SubHead>
          <SelectField label={t('part_downside')} tip={t('tip_part_downside')} value={terms.participation_downside ?? 'full'}
                       options={downsideOpts}
                       onChange={(v) => onChange(withDownside(terms, v as NonNullable<NoteTerms['participation_downside']>))} />
          <NumField label={t('protection_level')} tip={t('tip_protection_level')} value={terms.protection_level ?? 1.0} pct suffix="%"
                    onChange={(v) => set('protection_level', v)} />
          {terms.participation_downside === 'bear' && (<>
            <NumField label={t('participation_strike')} tip={t('tip_participation_strike')} value={terms.participation_strike ?? 1.0} pct suffix="%"
                      onChange={(v) => set('participation_strike', v)} />
            <NumField label={t('participation_rate')} tip={t('tip_participation_rate')} value={terms.participation_rate ?? 1.0} pct suffix="%"
                      onChange={(v) => set('participation_rate', v)} />
            {!periodic && (<>
              <ToggleField label={t('cap_upside')} tip={t('tip_cap_upside')} checked={terms.upside_cap != null}
                           onChange={(on) => set('upside_cap', on ? 0.5 : null)} />
              {terms.upside_cap != null && (
                <NumField label={t('upside_cap')} tip={t('tip_upside_cap')} value={terms.upside_cap} pct suffix="%"
                          onChange={(v) => set('upside_cap', v)} />
              )}
            </>)}
          </>)}
          {terms.participation_downside !== 'bear' && (<>
            <SubHead>{t('grp_upside')}</SubHead>
            <SelectField label={t('part_upside')} tip={t('tip_part_upside')} value={pu}
                         options={upsideOpts}
                         onChange={(v) => onChange(withUpside(terms, v as NonNullable<NoteTerms['participation_upside']>))} />
            <NumField label={t('participation_strike')} tip={t('tip_participation_strike')} value={terms.participation_strike ?? 1.0} pct suffix="%"
                      onChange={(v) => set('participation_strike', v)} />
            {pu !== 'digital' && (
              <NumField label={t('participation_rate')} tip={t('tip_participation_rate')} value={terms.participation_rate ?? 1.0} pct suffix="%"
                        onChange={(v) => set('participation_rate', v)} />
            )}
            {pu === 'shark_fin' && (<>
              <NumField label={t('knockout_level')} tip={t('tip_knockout_level')} value={terms.knockout_level ?? 1.3} pct suffix="%"
                        onChange={(v) => set('knockout_level', v)} />
              <NumField label={t('knockout_payout')} tip={t('tip_knockout_payout')} value={terms.knockout_payout ?? 1.0} pct suffix="%"
                        onChange={(v) => set('knockout_payout', v)} />
            </>)}
            {pu === 'digital' && (
              <NumField label={t('digital_payout')} tip={t('tip_digital_payout')} value={terms.digital_payout ?? 0} pct suffix="%"
                        onChange={(v) => set('digital_payout', v)} />
            )}
            {pu === 'linear' && !periodic && (<>
              <ToggleField label={t('cap_upside')} tip={t('tip_cap_upside')} checked={terms.upside_cap != null}
                           onChange={(on) => set('upside_cap', on ? 0.5 : null)} />
              {terms.upside_cap != null && (
                <NumField label={t('upside_cap')} tip={t('tip_upside_cap')} value={terms.upside_cap} pct suffix="%"
                          onChange={(v) => set('upside_cap', v)} />
              )}
            </>)}
          </>)}
          <SubHead>{t('grp_basket')}</SubHead>
          <SelectField label={t('part_basket')} tip={t('tip_part_basket')} value={terms.participation_basket ?? 'worst_of'}
                       options={BASKETS.map((b) => ({ value: b, label: t(`basket_${b}`) }))}
                       onChange={(v) => set('participation_basket', v)} />
        </>) : (<>
          <SegmentedField label={t('frequency')} value={terms.payment_freq} tip={t('tip_frequency')}
                          options={FREQS.map((f) => ({ value: f, label: FREQ_SHORT[f] }))}
                          onChange={(v) => set('payment_freq', v)} />
          <NumField label={t('coupon_pa')} value={terms.coupon_pa} pct suffix="%" tip={t('tip_coupon_pa')}
                    onChange={(v) => set('coupon_pa', v)} />
          <NumField label={t('coupon_barrier')} value={terms.coupon_barrier} pct suffix="%" tip={t('tip_coupon_barrier')}
                    onChange={(v) => set('coupon_barrier', v)} />
          <NumField label={t('knock_in_barrier')} value={terms.knock_in_barrier} pct suffix="%" tone="danger" tip={t('tip_knock_in')}
                    onChange={(v) => set('knock_in_barrier', v)} />
          <NumField label={t('autocall_barrier')} value={terms.autocall_barrier} pct suffix="%" tip={t('tip_autocall')}
                    onChange={(v) => set('autocall_barrier', v)} />
        </>)}
      </div>

      {/* Second group — the next-most-edited mechanics, inline so they don't
          require the settings overlay. Phoenix-family only; a Participation note's
          extra options all live in the settings overlay. */}
      {!isPart && (
      <div data-tour="mechanics" style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12 }}>{t('quick_mechanics')}</div>

        <NumField label={t('autocall_start')} value={Math.min(terms.autocall_start_period, nObs(terms))}
                  isInt min={1} max={Math.max(1, nObs(terms))}
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
          <NumField label={t('one_star_level')} value={terms.one_star_level} pct suffix="%"
                    onChange={(v) => set('one_star_level', v)} />
        )}
      </div>
      )}

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
