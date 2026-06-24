import { useI18n } from '../i18n/I18nProvider'
import { pct } from '../lib/format'
import Icon from './Icon'
import TickerLogo from './TickerLogo'
import type { ConfigMeta, NoteTerms } from '../api/types'

export interface RunOpts {
  n_paths: number
  engine: 'numpy' | 'cpp'
  seed: number
  calib_years: number
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '5px 0', fontSize: 12.5 }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className="mono" style={{ color: 'var(--text)' }}>{value}</span>
    </div>
  )
}

export default function SetupRail({
  terms, configs, configFile, onSelectConfig, opts, running, stale, onRun, onOpenSettings,
}: {
  terms: NoteTerms
  configs: ConfigMeta[]
  configFile: string
  onSelectConfig: (file: string) => void
  opts: RunOpts
  running: boolean
  stale: boolean
  onRun: () => void
  onOpenSettings: () => void
}) {
  const { t } = useI18n()
  const freqLabel = t(`freq_${terms.payment_freq}`)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('config_label')}</label>
        <select value={configFile} onChange={(e) => onSelectConfig(e.target.value)}>
          {configs.map((c) => <option key={c.file} value={c.file}>{c.name}</option>)}
        </select>
      </div>

      <div>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 8 }}>{t('underlyings')}</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
          {Object.entries(terms.tickers ?? {}).map(([sym, name]) => (
            <span key={sym} className="pill" style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)', paddingLeft: 5 }}>
              <TickerLogo symbol={sym} name={name} size={17} />{name}
            </span>
          ))}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>{t('current_terms')}</div>
        <div style={{ borderTop: '1px solid var(--border)' }}>
          <Row label={t('maturity')} value={`${terms.maturity}y · ${freqLabel.toLowerCase()}`} />
          <Row label={t('coupon_pa')} value={pct(terms.coupon_pa, 1)} />
          <Row label={t('coupon_barrier')} value={pct(terms.coupon_barrier, 0)} />
          <Row label={t('knock_in_barrier')} value={pct(terms.knock_in_barrier, 0)} />
          <Row label={t('autocall_barrier')} value={`${pct(terms.autocall_barrier, 0)} · P${terms.autocall_start_period}+`} />
          <Row label={t('memory')} value={terms.memory ? t('yes') : t('no')} />
          <Row label={t('paths')} value={`${opts.n_paths.toLocaleString()} · ${opts.engine}`} />
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
