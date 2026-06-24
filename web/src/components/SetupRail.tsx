import { useI18n } from '../i18n/I18nProvider'
import { pct } from '../lib/format'
import { nObs } from '../lib/terms'
import Icon from './Icon'
import TickerLogo from './TickerLogo'
import type { ConfigMeta, NoteTerms } from '../api/types'

export interface RunOpts {
  n_paths: number
  engine: 'numpy' | 'cpp'
}

const PATH_PRESETS = [2000, 5000, 10000, 25000, 50000, 100000, 250000]
const FREQS: NoteTerms['payment_freq'][] = ['monthly', 'quarterly', 'semi-annual', 'annual']

function Slider({
  label, value, min, max, step, fmt, onChange,
}: {
  label: string; value: number; min: number; max: number; step: number
  fmt: (n: number) => string; onChange: (v: number) => void
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
        <span className="mono" style={{ fontSize: 12, color: 'var(--text)' }}>{fmt(value)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
             onChange={(e) => onChange(parseFloat(e.target.value))} />
    </div>
  )
}

export default function SetupRail({
  terms, onChange, configs, configFile, onSelectConfig,
  opts, onOptsChange, cppAvailable, running, stale, onRun,
}: {
  terms: NoteTerms
  onChange: (t: NoteTerms) => void
  configs: ConfigMeta[]
  configFile: string
  onSelectConfig: (file: string) => void
  opts: RunOpts
  onOptsChange: (o: RunOpts) => void
  cppAvailable: boolean
  running: boolean
  stale: boolean
  onRun: () => void
}) {
  const { t } = useI18n()
  const set = <K extends keyof NoteTerms>(k: K, v: NoteTerms[K]) => onChange({ ...terms, [k]: v })
  const n = nObs(terms)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('config_label')}</label>
        <select value={configFile} onChange={(e) => onSelectConfig(e.target.value)}>
          {configs.map((c) => (
            <option key={c.file} value={c.file}>{c.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 8 }}>{t('underlyings')}</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
          {Object.entries(terms.tickers ?? {}).map(([sym, name]) => (
            <span key={sym} className="pill"
                  style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)', paddingLeft: 5 }}>
              <TickerLogo symbol={sym} name={name} size={17} />{name}
            </span>
          ))}
        </div>
      </div>

      <div style={{ height: 1, background: 'var(--border)' }} />

      <Slider label={t('maturity')} value={terms.maturity} min={0.25} max={5} step={0.25}
              fmt={(v) => `${v.toFixed(2)} y`} onChange={(v) => set('maturity', v)} />
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('frequency')}</label>
        <select value={terms.payment_freq} onChange={(e) => set('payment_freq', e.target.value as NoteTerms['payment_freq'])}>
          {FREQS.map((f) => <option key={f} value={f}>{t(`freq_${f}`)}</option>)}
        </select>
      </div>
      <Slider label={t('coupon_pa')} value={terms.coupon_pa} min={0} max={0.3} step={0.005}
              fmt={(v) => pct(v, 1)} onChange={(v) => set('coupon_pa', v)} />
      <Slider label={t('autocall_barrier')} value={terms.autocall_barrier} min={0.5} max={1.2} step={0.01}
              fmt={(v) => pct(v, 0)} onChange={(v) => set('autocall_barrier', v)} />
      <Slider label={t('coupon_barrier')} value={terms.coupon_barrier} min={0.3} max={1.0} step={0.01}
              fmt={(v) => pct(v, 0)} onChange={(v) => set('coupon_barrier', v)} />
      <Slider label={t('knock_in_barrier')} value={terms.knock_in_barrier} min={0.2} max={1.0} step={0.01}
              fmt={(v) => pct(v, 0)} onChange={(v) => set('knock_in_barrier', v)} />
      <Slider label={t('autocall_start')} value={Math.min(terms.autocall_start_period, n)} min={1} max={n} step={1}
              fmt={(v) => `P${v}`} onChange={(v) => set('autocall_start_period', v)} />

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer' }}>
        <input type="checkbox" checked={terms.memory} onChange={(e) => set('memory', e.target.checked)}
               style={{ width: 'auto' }} />
        {t('memory')}
      </label>

      <div style={{ height: 1, background: 'var(--border)' }} />

      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('paths')}</label>
          <select value={opts.n_paths} onChange={(e) => onOptsChange({ ...opts, n_paths: parseInt(e.target.value) })}>
            {PATH_PRESETS.map((p) => <option key={p} value={p}>{p.toLocaleString()}</option>)}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('engine')}</label>
          <select value={opts.engine} onChange={(e) => onOptsChange({ ...opts, engine: e.target.value as RunOpts['engine'] })}>
            <option value="numpy">numpy</option>
            <option value="cpp" disabled={!cppAvailable}>C++{cppAvailable ? '' : ' (n/a)'}</option>
          </select>
        </div>
      </div>

      <button className={`btn btn--primary${stale && !running ? ' btn--pulse' : ''}`}
              style={{ justifyContent: 'center', padding: '12px', fontSize: 14 }}
              disabled={running} onClick={onRun}>
        <Icon name={running ? 'spinner' : stale ? 'refresh' : 'play'} size={16} />
        {running ? t('running') : stale ? t('rerun') : t('run')}
      </button>
    </div>
  )
}
