import type { ReactNode } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { nObs } from '../lib/terms'
import Modal from './Modal'
import Icon from './Icon'
import UnderlyingPicker from './UnderlyingPicker'
import UnderlyingDetails from './UnderlyingDetails'
import { Slider, NumField, NumberField, SelectField, SegmentedField, ToggleField, TextField } from './fields'
import { NOTE_TYPES, detectNoteType, applyPreset } from '../lib/noteType'
import { withDownside, withUpside } from '../lib/participation'
import type { RunOpts } from './SetupRail'
import type { Basket, NoteTerms } from '../api/types'

const FREQS: NoteTerms['payment_freq'][] = ['monthly', 'quarterly', 'semi-annual', 'annual']
const PATH_PRESETS = [2000, 5000, 10000, 25000, 50000, 100000, 250000]
const CALIB_YEARS = [1, 2, 3, 5, 10]

function Group({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section style={{ marginBottom: 26 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{
          width: 22, height: 22, borderRadius: 7, background: 'var(--accent-weak)', color: 'var(--accent-text)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600,
        }}>{n}</span>
        <span style={{ fontSize: 13.5, fontWeight: 600 }}>{title}</span>
      </div>
      {children}
    </section>
  )
}

function Grid({ children }: { children: ReactNode }) {
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', columnGap: 22 }}>{children}</div>
}

export default function SettingsOverlay({
  terms, onChange, opts, onOptsChange, cppAvailable, onClose, onRun,
}: {
  terms: NoteTerms
  onChange: (t: NoteTerms) => void
  opts: RunOpts
  onOptsChange: (o: RunOpts) => void
  cppAvailable: boolean
  onClose: () => void
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
  const activeType = detectNoteType(terms)
  const isPart = activeType === 'participation'
  const periodic = terms.participation_periodic ?? false
  const pd = terms.participation_downside ?? 'full'
  const pu = terms.participation_upside ?? 'linear'
  const downsideOpts = (['full', 'buffer', 'airbag', 'bear'] as const).map((v) => ({ value: v, label: t(`pd_${v}`) }))
  const upsideOpts = (['linear', 'shark_fin', 'digital'] as const).map((v) => ({ value: v, label: t(`pu_${v}`) }))
  // Label for the protection level shifts with the downside style.
  const protLabel = pd === 'airbag' ? t('knock_in_barrier') : t('protection_level')

  return (
    <Modal title={t('setup_heading')} onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>{t('done')}</button>
        <button className="btn btn--primary" onClick={() => { onRun(); onClose() }}>
          <Icon name="play" size={15} /> {t('run')}
        </button>
      </>}>

      <Group n={0} title={t('sec_note_type')}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>{t('nt_hint')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          {NOTE_TYPES.map((nt) => {
            const on = nt === activeType
            return (
              <button key={nt} onClick={() => onChange(applyPreset(terms, nt))}
                style={{
                  textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', padding: '11px 13px', borderRadius: 11,
                  border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`,
                  background: on ? 'var(--accent-weak)' : 'var(--surface)',
                  transition: 'border-color .12s ease, background .12s ease',
                }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: on ? 'var(--accent-text)' : 'var(--text)' }}>{t(`nt_${nt}`)}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.45 }}>{t(`nt_${nt}_desc`)}</div>
              </button>
            )
          })}
        </div>
      </Group>

      <Group n={1} title={t('underlyings')}>
        <UnderlyingPicker tickers={terms.tickers} onChange={(tk) => set('tickers', tk)} />
      </Group>

      {isPart && (
      <Group n={2} title={t('sec_participation')}>
        <Grid>
          <Slider label={t('maturity')} value={terms.maturity} min={0.25} max={5} step={0.25}
                  editSuffix="y" fmt={(v) => `${v.toFixed(2)} y`} onChange={(v) => set('maturity', v)} />
          <SelectField label={t('part_basket')} value={terms.participation_basket ?? 'worst_of'} options={basketOpts}
                       onChange={(v) => set('participation_basket', v)} />
        </Grid>
        {/* Cliquet / periodic toggle — a series of back-to-back protected
            participation notes paying the participation each reset period. */}
        <div style={{ marginTop: 8 }}>
          <ToggleField label={t('part_periodic')} checked={periodic}
                       onChange={(v) => set('participation_periodic', v)} />
          <div style={{ fontSize: 11, color: 'var(--text-faint)', margin: '4px 0 10px', lineHeight: 1.5 }}>{t('part_periodic_h')}</div>
        </div>

        {periodic ? (
          <>
            <div style={{ gridColumn: '1 / -1', maxWidth: 480, marginBottom: 12 }}>
              <SegmentedField label={t('part_reset')} value={terms.payment_freq}
                              options={FREQS.map((f) => ({ value: f, label: t(`freq_${f}`) }))} onChange={(v) => set('payment_freq', v)} />
            </div>
            <Grid>
              <NumberField label={t('participation_rate')} value={terms.participation_rate ?? 1.0} percent suffix="%" min={0} max={500} step={5}
                           onChange={(v) => set('participation_rate', v)} />
              <NumberField label={t('protection_level')} value={terms.protection_level ?? 1.0} percent suffix="%" min={0} max={100} step={1}
                           onChange={(v) => set('protection_level', v)} />
              <div>
                <ToggleField label={t('cap_period')} checked={terms.period_cap != null}
                             onChange={(v) => set('period_cap', v ? 0.08 : null)} />
                {terms.period_cap != null && (
                  <NumberField label={t('period_cap')} value={terms.period_cap} percent suffix="%" min={0} max={50} step={0.5}
                               onChange={(v) => set('period_cap', v)} />
                )}
              </div>
            </Grid>
          </>
        ) : (<>
          <div>
            <SelectField label={t('part_downside')} value={pd}
                         options={downsideOpts} onChange={(v) => onChange(withDownside(terms, v as NonNullable<NoteTerms['participation_downside']>))} />
            <div style={{ fontSize: 11, color: 'var(--text-faint)', margin: '4px 0 10px', lineHeight: 1.5 }}>{t(`pd_${pd}_h`)}</div>
          </div>
          {pd !== 'bear' && (
            <div>
              <SelectField label={t('part_upside')} value={pu}
                           options={upsideOpts} onChange={(v) => onChange(withUpside(terms, v as NonNullable<NoteTerms['participation_upside']>))} />
              <div style={{ fontSize: 11, color: 'var(--text-faint)', margin: '4px 0 10px', lineHeight: 1.5 }}>{t(`pu_${pu}_h`)}</div>
            </div>
          )}
          <Grid>
            <NumberField label={protLabel} value={terms.protection_level ?? 1.0} percent suffix="%" min={0} max={120} step={1}
                         onChange={(v) => set('protection_level', v)} />
            <NumberField label={t('participation_strike')} value={terms.participation_strike ?? 1.0} percent suffix="%" min={50} max={150} step={0.5}
                         onChange={(v) => set('participation_strike', v)} />
            {(pd === 'bear' || pu !== 'digital') && (
              <NumberField label={t('participation_rate')} value={terms.participation_rate ?? 1.0} percent suffix="%" min={0} max={500} step={5}
                           onChange={(v) => set('participation_rate', v)} />
            )}
            {pu === 'shark_fin' && pd !== 'bear' && (
              <NumberField label={t('knockout_level')} value={terms.knockout_level ?? 1.3} percent suffix="%" min={100} max={400} step={1}
                           onChange={(v) => set('knockout_level', v)} />
            )}
            {pu === 'shark_fin' && pd !== 'bear' && (
              <NumberField label={t('knockout_payout')} value={terms.knockout_payout ?? 1.0} percent suffix="%" min={0} max={200} step={0.5}
                           onChange={(v) => set('knockout_payout', v)} />
            )}
            {pu === 'digital' && pd !== 'bear' && (
              <NumberField label={t('digital_payout')} value={terms.digital_payout ?? 0} percent suffix="%" min={0} max={200} step={0.5}
                           onChange={(v) => set('digital_payout', v)} />
            )}
            {(pd === 'bear' || pu === 'linear') && (
              <div>
                <ToggleField label={t('cap_upside')} checked={terms.upside_cap != null}
                             onChange={(v) => set('upside_cap', v ? 0.5 : null)} />
                {terms.upside_cap != null && (
                  <NumberField label={t('upside_cap')} value={terms.upside_cap} percent suffix="%" min={0} max={300} step={5}
                               onChange={(v) => set('upside_cap', v)} />
                )}
              </div>
            )}
          </Grid>
        </>)}
      </Group>
      )}

      {!isPart && (<>
      <Group n={2} title={t('sec_schedule_coupon')}>
        <Grid>
          {/* Own row (span all columns) so all four frequency options fit without
              being clipped, but capped so it isn't stretched on wide screens. */}
          <div style={{ gridColumn: '1 / -1', maxWidth: 480 }}>
            <SegmentedField label={t('frequency')} value={terms.payment_freq}
                            options={FREQS.map((f) => ({ value: f, label: t(`freq_${f}`) }))} onChange={(v) => set('payment_freq', v)} />
          </div>
          <Slider label={t('maturity')} value={terms.maturity} min={0.25} max={5} step={0.25}
                  editSuffix="y" fmt={(v) => `${v.toFixed(2)} y`} onChange={(v) => set('maturity', v)} />
          <NumField label={t('coupon_pa')} value={terms.coupon_pa} pct suffix="%"
                    onChange={(v) => set('coupon_pa', v)} />
          <SelectField label={t('coupon_basket')} value={terms.coupon_basket} options={basketOpts} onChange={(v) => set('coupon_basket', v)} />
          <NumberField label={t('coupon_barrier')} value={terms.coupon_barrier} percent suffix="%" min={0} max={100} step={0.5}
                       onChange={(v) => set('coupon_barrier', v)} />
        </Grid>
        <ToggleField label={t('memory')} checked={terms.memory} onChange={(v) => set('memory', v)} />
      </Group>

      <Group n={3} title={t('sec_protection')}>
        <Grid>
          <NumberField label={t('knock_in_barrier')} value={terms.knock_in_barrier} percent suffix="%" min={0} max={100} step={0.5}
                       error={terms.knock_in_barrier > 1 ? t('barrier_max') : undefined}
                       onChange={(v) => set('knock_in_barrier', v)} />
        </Grid>
        <Grid>
          <div>
            <ToggleField label={t('capital_protected')} checked={(terms.capital_guarantee ?? 0) > 0}
                         onChange={(v) => set('capital_guarantee', v ? 1.0 : 0)} />
            {(terms.capital_guarantee ?? 0) > 0 && (
              <NumberField label={t('capital_guarantee')} value={terms.capital_guarantee} percent suffix="%" min={0} max={100} step={1}
                           onChange={(v) => set('capital_guarantee', v)} />
            )}
          </div>
          <div>
            <ToggleField label={t('one_star')} checked={terms.one_star_level != null}
                         onChange={(v) => set('one_star_level', v ? 1.0 : null)} />
            {terms.one_star_level != null && (<>
              <NumberField label={t('one_star_level')} value={terms.one_star_level} percent suffix="%" min={50} max={150} step={0.5}
                           onChange={(v) => set('one_star_level', v)} />
              <div style={{ fontSize: 11, color: 'var(--text-faint)', margin: '4px 0 8px', lineHeight: 1.5 }}>{t('one_star_scope_hint')}</div>
              <ToggleField label={t('one_star_coupon')} checked={!!terms.one_star_coupon}
                           onChange={(v) => set('one_star_coupon', v)} />
              <ToggleField label={t('one_star_autocall')} checked={!!terms.one_star_autocall}
                           onChange={(v) => set('one_star_autocall', v)} />
            </>)}
          </div>
          {(terms.capital_guarantee ?? 0) > 0 && (
            <div>
              <ToggleField label={t('cap_upside')} checked={terms.upside_cap != null}
                           onChange={(v) => set('upside_cap', v ? 1.5 : null)} />
              {terms.upside_cap != null && (
                <NumberField label={t('upside_cap')} value={terms.upside_cap} percent suffix="%" min={100} max={300} step={5}
                             onChange={(v) => set('upside_cap', v)} />
              )}
            </div>
          )}
        </Grid>
      </Group>

      <Group n={4} title={t('sec_autocall')}>
        <Grid>
          <NumberField label={t('autocall_barrier')} value={terms.autocall_barrier} percent suffix="%" min={50} max={300} step={0.5}
                       onChange={(v) => set('autocall_barrier', v)} />
          <Slider label={t('autocall_start')} value={Math.min(terms.autocall_start_period, n)} min={1} max={n} step={1}
                  editInt editPrefix="P" editClamp={[1, n]} fmt={(v) => `P${v}`} onChange={(v) => set('autocall_start_period', v)} />
          <SelectField label={t('autocall_basket')} value={terms.autocall_basket} options={basketOpts} onChange={(v) => set('autocall_basket', v)} />
          <NumberField label={t('step_down')} value={stepDown} percent suffix="%" min={0} max={10} step={0.5}
                       onChange={(v) => set('autocall_step_down', v || null)} />
          {stepDown > 0 && (
            <NumberField label={t('autocall_floor')} value={terms.autocall_floor ?? 0} percent suffix="%" min={0} max={100} step={1}
                         onChange={(v) => set('autocall_floor', v || null)} />
          )}
        </Grid>
        <ToggleField label={t('premium_at_call')} checked={!!terms.coupon_at_autocall_only}
                     onChange={(v) => set('coupon_at_autocall_only', v)} />
      </Group>
      </>)}

      <Group n={5} title={t('sec_metadata')}>
        <Grid>
          <TextField label={t('note_name')} value={terms.name ?? ''} onChange={(v) => set('name', v)} />
          <TextField label={t('issuer_name')} value={terms.issuer ?? ''} onChange={(v) => set('issuer', v)} placeholder="e.g. BBVA, HSBC" />
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('issue_date')}</label>
            <input type="date" value={terms.issue_date ?? ''} onChange={(e) => set('issue_date', e.target.value || null)} />
          </div>
          <TextField label={t('rating_sp')} value={terms.issuer_rating_sp ?? ''} onChange={(v) => set('issuer_rating_sp', v)} placeholder="A+" />
          <TextField label={t('rating_moody')} value={terms.issuer_rating_moody ?? ''} onChange={(v) => set('issuer_rating_moody', v)} placeholder="A1" />
          <TextField label={t('rating_fitch')} value={terms.issuer_rating_fitch ?? ''} onChange={(v) => set('issuer_rating_fitch', v)} placeholder="AA-" />
        </Grid>
      </Group>

      <Group n={6} title={t('sec_details')}>
        <UnderlyingDetails terms={terms} onChange={onChange} />
      </Group>

      <Group n={7} title={t('sec_engine')}>
        <Grid>
          <SelectField label={t('paths')} value={String(opts.n_paths)}
                       options={PATH_PRESETS.map((p) => ({ value: String(p), label: p.toLocaleString() }))}
                       onChange={(v) => onOptsChange({ ...opts, n_paths: parseInt(v) })} />
          <SegmentedField label={t('engine')} value={opts.engine}
                          options={[{ value: 'numpy', label: 'numpy' }, { value: 'cpp', label: cppAvailable ? 'C++' : 'C++ (fallback)' }]}
                          onChange={(v) => onOptsChange({ ...opts, engine: v === 'cpp' ? 'cpp' : 'numpy' })} />
          <NumberField label={t('seed')} value={opts.seed} step={1} min={0} onChange={(v) => onOptsChange({ ...opts, seed: Math.round(v) })} />
          <SelectField label={t('calib_window')} value={String(opts.calib_years)}
                       options={CALIB_YEARS.map((y) => ({ value: String(y), label: `${y} ${t('calib_years')}` }))}
                       onChange={(v) => onOptsChange({ ...opts, calib_years: parseInt(v) })} />
        </Grid>
      </Group>
    </Modal>
  )
}
