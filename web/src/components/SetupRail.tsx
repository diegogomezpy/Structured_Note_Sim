import { useRef, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { pct } from '../lib/format'
import Icon from './Icon'
import { Slider, SelectField } from './fields'
import AddNoteHelp from './AddNoteHelp'
import UnderlyingPicker from './UnderlyingPicker'
import type { ConfigMeta, NoteTerms } from '../api/types'

export interface RunOpts {
  n_paths: number
  engine: 'numpy' | 'cpp'
  seed: number
  calib_years: number
}

const FREQS: NoteTerms['payment_freq'][] = ['monthly', 'quarterly', 'semi-annual', 'annual']

/** Compact percentage input (stored as a fraction, edited as a %) for the
    barrier row — narrow enough to sit three-across in the rail. */
function Barrier({ label, value, onChange, min = 0, max = 300, tip }: {
  label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; tip?: string
}) {
  return (
    <div>
      <div title={tip} style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 5, whiteSpace: 'nowrap', cursor: tip ? 'help' : undefined }}>{label}</div>
      <div style={{ position: 'relative' }}>
        <input type="number" value={Math.round(value * 1000) / 10} min={min} max={max} step={0.5}
               onChange={(e) => { const v = parseFloat(e.target.value); if (!Number.isNaN(v)) onChange(v / 100) }}
               style={{ textAlign: 'right', paddingRight: 20 }} />
        <span style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: 'var(--text-faint)', pointerEvents: 'none' }}>%</span>
      </div>
    </div>
  )
}

export default function SetupRail({
  terms, onChange, configs, configFile, onSelectConfig, onUploadConfig, opts, running, stale, onRun, onOpenSettings,
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
  const set = <K extends keyof NoteTerms>(k: K, v: NoteTerms[K]) => onChange({ ...terms, [k]: v })
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploadErr, setUploadErr] = useState('')

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('config_label')}</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <AddNoteHelp />
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
        <select value={configFile} onChange={(e) => onSelectConfig(e.target.value)}>
          <option value="">{t('blank_note')}</option>
          {configs.map((c) => <option key={c.file} value={c.file}>{c.name}</option>)}
        </select>
        {uploadErr && <div style={{ fontSize: 11.5, color: 'var(--red)', marginTop: 5 }}>{uploadErr}</div>}
      </div>

      <UnderlyingPicker tickers={terms.tickers} onChange={(tk) => set('tickers', tk)} />

      {/* Lean inline editor for the terms that drive the note diagram above —
          maturity / schedule / coupon and the three barriers. Everything else
          lives in the full settings overlay. */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12 }}>{t('quick_edit')}</div>

        <Slider label={t('maturity')} value={terms.maturity} min={0.25} max={5} step={0.25} tip={t('tip_maturity')}
                fmt={(v) => `${v.toFixed(2)} y`} onChange={(v) => set('maturity', v)} />
        <SelectField label={t('frequency')} value={terms.payment_freq} tip={t('tip_frequency')}
                     options={FREQS.map((f) => ({ value: f, label: t(`freq_${f}`) }))}
                     onChange={(v) => set('payment_freq', v)} />
        <Slider label={t('coupon_pa')} value={terms.coupon_pa} min={0} max={0.3} step={0.005} tip={t('tip_coupon_pa')}
                fmt={(v) => pct(v, 1)} onChange={(v) => set('coupon_pa', v)} />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 2 }}>
          <Barrier label={t('coupon_barrier_short')} value={terms.coupon_barrier} onChange={(v) => set('coupon_barrier', v)} tip={t('tip_coupon_barrier')} />
          <Barrier label={t('knock_in_short')} value={terms.knock_in_barrier} onChange={(v) => set('knock_in_barrier', v)} tip={t('tip_knock_in')} />
          <Barrier label={t('autocall_short')} value={terms.autocall_barrier} min={50} onChange={(v) => set('autocall_barrier', v)} tip={t('tip_autocall')} />
        </div>
      </div>

      <button className="btn" style={{ justifyContent: 'center', padding: '10px' }} onClick={onOpenSettings}>
        <Icon name="chart" size={15} /> {t('edit_settings')}
      </button>

      <button className={`btn btn--primary${stale && !running ? ' btn--pulse' : ''}`}
              style={{ justifyContent: 'center', padding: '12px', fontSize: 14 }}
              disabled={running} onClick={onRun}>
        <Icon name={running ? 'spinner' : stale ? 'refresh' : 'play'} size={16} />
        {running ? t('running') : stale ? t('rerun') : t('run')}
      </button>
    </div>
  )
}
