import { useI18n } from '../i18n/I18nProvider'
import { pct } from '../lib/format'
import { nObs } from '../lib/terms'
import Icon from './Icon'
import UnderlyingPicker from './UnderlyingPicker'
import { Slider, NumberField, SelectField, ToggleField, TextField, Section } from './fields'
import type { Basket, ConfigMeta, NoteTerms } from '../api/types'

export interface RunOpts {
  n_paths: number
  engine: 'numpy' | 'cpp'
  seed: number
  calib_years: number
}

const PATH_PRESETS = [2000, 5000, 10000, 25000, 50000, 100000, 250000]
const FREQS: NoteTerms['payment_freq'][] = ['monthly', 'quarterly', 'semi-annual', 'annual']
const CALIB_YEARS = [1, 2, 3, 5, 10]

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

  const basketOpts = [
    { value: 'worst_of' as Basket, label: t('basket_worst_of') },
    { value: 'best_of' as Basket, label: t('basket_best_of') },
    { value: 'average' as Basket, label: t('basket_average') },
  ]
  const stepDown = terms.autocall_step_down ?? 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('config_label')}</label>
        <select value={configFile} onChange={(e) => onSelectConfig(e.target.value)}>
          {configs.map((c) => <option key={c.file} value={c.file}>{c.name}</option>)}
        </select>
      </div>

      <UnderlyingPicker tickers={terms.tickers} onChange={(tk) => set('tickers', tk)} />

      <div style={{ height: 1, background: 'var(--border)', margin: '14px 0' }} />

      {/* core terms */}
      <Slider label={t('maturity')} value={terms.maturity} min={0.25} max={5} step={0.25}
              fmt={(v) => `${v.toFixed(2)} y`} onChange={(v) => set('maturity', v)} />
      <SelectField label={t('frequency')} value={terms.payment_freq}
                   options={FREQS.map((f) => ({ value: f, label: t(`freq_${f}`) }))}
                   onChange={(v) => set('payment_freq', v)} />
      <Slider label={t('coupon_pa')} value={terms.coupon_pa} min={0} max={0.3} step={0.005}
              fmt={(v) => pct(v, 1)} onChange={(v) => set('coupon_pa', v)} />
      <Slider label={t('autocall_barrier')} value={terms.autocall_barrier} min={0.5} max={2.0} step={0.01}
              fmt={(v) => pct(v, 0)} onChange={(v) => set('autocall_barrier', v)} />
      <Slider label={t('coupon_barrier')} value={terms.coupon_barrier} min={0} max={1.0} step={0.01}
              fmt={(v) => pct(v, 0)} onChange={(v) => set('coupon_barrier', v)} />
      <Slider label={t('knock_in_barrier')} value={terms.knock_in_barrier} min={0} max={1.0} step={0.01}
              fmt={(v) => pct(v, 0)} onChange={(v) => set('knock_in_barrier', v)} />
      <Slider label={t('autocall_start')} value={Math.min(terms.autocall_start_period, n)} min={1} max={n} step={1}
              fmt={(v) => `P${v}`} onChange={(v) => set('autocall_start_period', v)} />
      <ToggleField label={t('memory')} checked={terms.memory} onChange={(v) => set('memory', v)} />

      {/* baskets & overlays */}
      <Section title={t('sec_basket')}>
        <SelectField label={t('coupon_basket')} value={terms.coupon_basket} options={basketOpts} onChange={(v) => set('coupon_basket', v)} />
        <SelectField label={t('autocall_basket')} value={terms.autocall_basket} options={basketOpts} onChange={(v) => set('autocall_basket', v)} />
        <ToggleField label={t('one_star')} checked={terms.one_star_level != null}
                     onChange={(v) => set('one_star_level', v ? 1.0 : null)} />
        {terms.one_star_level != null && (
          <NumberField label={t('one_star_level')} value={terms.one_star_level} percent suffix="%"
                       min={50} max={150} step={0.5} onChange={(v) => set('one_star_level', v)} />
        )}
      </Section>

      {/* autocall schedule */}
      <Section title={t('sec_autocall')}>
        <NumberField label={t('step_down')} value={stepDown} percent suffix="%" min={0} max={0.1} step={0.005}
                     onChange={(v) => set('autocall_step_down', v || null)} />
        {stepDown > 0 && (
          <NumberField label={t('autocall_floor')} value={terms.autocall_floor ?? 0} percent suffix="%" min={0} max={1} step={0.01}
                       onChange={(v) => set('autocall_floor', v || null)} />
        )}
        <ToggleField label={t('premium_at_call')} checked={!!terms.coupon_at_autocall_only}
                     onChange={(v) => set('coupon_at_autocall_only', v)} />
      </Section>

      {/* protection */}
      <Section title={t('sec_protection')}>
        <NumberField label={t('min_return')} value={terms.min_return ?? 0} percent suffix="%" min={0} max={1} step={0.01}
                     onChange={(v) => set('min_return', v)} />
        <ToggleField label={t('capital_protected')} checked={(terms.capital_guarantee ?? 0) > 0}
                     onChange={(v) => set('capital_guarantee', v ? 1.0 : 0)} />
        {(terms.capital_guarantee ?? 0) > 0 && (
          <>
            <NumberField label={t('capital_guarantee')} value={terms.capital_guarantee} percent suffix="%" min={0} max={1} step={0.01}
                         onChange={(v) => set('capital_guarantee', v)} />
            <ToggleField label={t('cap_upside')} checked={terms.upside_cap != null}
                         onChange={(v) => set('upside_cap', v ? 1.5 : null)} />
            {terms.upside_cap != null && (
              <NumberField label={t('upside_cap')} value={terms.upside_cap} percent suffix="%" min={1} max={3} step={0.05}
                           onChange={(v) => set('upside_cap', v)} />
            )}
          </>
        )}
      </Section>

      {/* issuer & dates */}
      <Section title={t('sec_metadata')}>
        <TextField label={t('note_name')} value={terms.name ?? ''} onChange={(v) => set('name', v)} />
        <TextField label={t('issuer_name')} value={terms.issuer ?? ''} onChange={(v) => set('issuer', v)} placeholder="e.g. BBVA, HSBC" />
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ flex: 1 }}><TextField label={t('rating_sp')} value={terms.issuer_rating_sp ?? ''} onChange={(v) => set('issuer_rating_sp', v)} placeholder="A+" /></div>
          <div style={{ flex: 1 }}><TextField label={t('rating_moody')} value={terms.issuer_rating_moody ?? ''} onChange={(v) => set('issuer_rating_moody', v)} placeholder="A1" /></div>
          <div style={{ flex: 1 }}><TextField label={t('rating_fitch')} value={terms.issuer_rating_fitch ?? ''} onChange={(v) => set('issuer_rating_fitch', v)} placeholder="AA-" /></div>
        </div>
        <div style={{ marginBottom: 4 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('issue_date')}</label>
          <input type="date" value={terms.issue_date ?? ''} onChange={(e) => set('issue_date', e.target.value || null)} />
        </div>
      </Section>

      {/* engine */}
      <Section title={t('sec_engine')} defaultOpen>
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
        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
          <div style={{ flex: 1 }}>
            <NumberField label={t('seed')} value={opts.seed} step={1} min={0}
                         onChange={(v) => onOptsChange({ ...opts, seed: Math.round(v) })} />
          </div>
          <div style={{ flex: 1 }}>
            <SelectField label={t('calib_window')} value={String(opts.calib_years)}
                         options={CALIB_YEARS.map((y) => ({ value: String(y), label: `${y} ${t('calib_years')}` }))}
                         onChange={(v) => onOptsChange({ ...opts, calib_years: parseInt(v) })} />
          </div>
        </div>
      </Section>

      <button className={`btn btn--primary${stale && !running ? ' btn--pulse' : ''}`}
              style={{ justifyContent: 'center', padding: '12px', fontSize: 14, marginTop: 14 }}
              disabled={running} onClick={onRun}>
        <Icon name={running ? 'spinner' : stale ? 'refresh' : 'play'} size={16} />
        {running ? t('running') : stale ? t('rerun') : t('run')}
      </button>
    </div>
  )
}
