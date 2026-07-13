import { useMemo, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { participationRedemption } from '../lib/participation'
import { pct } from '../lib/format'
import type { NoteTerms, SimSummary } from '../api/types'

/* What-if sensitivity — drag participation rate / cap / protection and watch the
   redemption metrics move instantly. Pure client-side: it re-scores the SAME
   simulated final-basket sample (summary.final_basket_sample) through the TS
   redemption mirror, so there's no re-simulation. Only the three levers that don't
   change the sim (they only reshape the maturity payoff) are exposed. */

function metrics(sample: number[], t: NoteTerms) {
  const R = sample.map((b) => participationRedemption(b, t)).sort((a, b) => a - b)
  const n = R.length
  const mean = R.reduce((s, x) => s + x, 0) / n
  const above = R.filter((x) => x > 1 + 1e-9).length / n
  const p5 = R[Math.max(0, Math.floor(0.05 * n) - 1)]
  return { mean, above, p5 }
}

function Slider({ label, value, min, max, step, fmt, onChange }: {
  label: string; value: number; min: number; max: number; step: number
  fmt: (v: number) => string; onChange: (v: number) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5 }}>
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{fmt(value)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
             onChange={(e) => onChange(parseFloat(e.target.value))}
             style={{ width: '100%', accentColor: 'var(--accent)' }} />
    </div>
  )
}

export default function ParticipationWhatIf({ terms, summary }: { terms: NoteTerms; summary: SimSummary }) {
  const { t } = useI18n()
  const sample = summary.final_basket_sample
  const [rate, setRate] = useState(terms.participation_rate ?? 1)
  const [prot, setProt] = useState(terms.protection_level ?? 1)
  const [capOn, setCapOn] = useState(terms.upside_cap != null)
  const [cap, setCap] = useState(terms.upside_cap ?? 0.5)

  const tweaked: NoteTerms = { ...terms, participation_rate: rate, protection_level: prot, upside_cap: capOn ? cap : null }
  const base = useMemo(() => sample ? metrics(sample, terms) : null, [sample, terms])
  const now = useMemo(() => sample ? metrics(sample, tweaked) : null,
    // recompute whenever a lever moves
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sample, rate, prot, capOn, cap])

  if (!sample || !sample.length || !base || !now) return null
  const dirty = rate !== (terms.participation_rate ?? 1) || prot !== (terms.protection_level ?? 1)
    || capOn !== (terms.upside_cap != null) || (capOn && cap !== (terms.upside_cap ?? 0.5))

  const reset = () => {
    setRate(terms.participation_rate ?? 1); setProt(terms.protection_level ?? 1)
    setCapOn(terms.upside_cap != null); setCap(terms.upside_cap ?? 0.5)
  }
  const row = (label: string, b: number, v: number, goodUp = true) => {
    const d = v - b
    const tone = Math.abs(d) < 5e-5 ? 'var(--text-faint)' : (d > 0) === goodUp ? 'var(--accent-text)' : 'var(--red)'
    return (
      <tr>
        <td style={{ padding: '6px 10px', color: 'var(--text-muted)' }}>{label}</td>
        <td style={{ padding: '6px 10px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{pct(b, 1)}</td>
        <td style={{ padding: '6px 10px', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{pct(v, 1)}</td>
        <td style={{ padding: '6px 10px', textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: tone }}>
          {Math.abs(d) < 5e-5 ? '—' : `${d > 0 ? '+' : ''}${pct(d, 1)}`}
        </td>
      </tr>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(200px, 1fr) minmax(240px, 1.2fr)', gap: 22, alignItems: 'start' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Slider label={t('participation_rate')} value={rate} min={0} max={3} step={0.05} fmt={(v) => pct(v, 0)} onChange={setRate} />
        <Slider label={t('protection_level')} value={prot} min={0} max={1.2} step={0.01} fmt={(v) => pct(v, 0)} onChange={setProt} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11.5, color: 'var(--text-muted)' }}>
            <input type="checkbox" checked={capOn} onChange={(e) => setCapOn(e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
            {t('cap_upside')}
          </label>
          {capOn && <Slider label={t('upside_cap')} value={cap} min={0} max={2} step={0.05} fmt={(v) => `+${pct(v, 0)}`} onChange={setCap} />}
        </div>
        {dirty && (
          <button className="btn btn--ghost" style={{ padding: '5px 11px', fontSize: 12, alignSelf: 'flex-start' }} onClick={reset}>
            {t('whatif_reset')}
          </button>
        )}
      </div>
      <div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-faint)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              <th style={{ padding: '4px 10px', textAlign: 'left' }}></th>
              <th style={{ padding: '4px 10px', textAlign: 'right' }}>{t('whatif_base')}</th>
              <th style={{ padding: '4px 10px', textAlign: 'right' }}>{t('whatif_now')}</th>
              <th style={{ padding: '4px 10px', textAlign: 'right' }}>Δ</th>
            </tr>
          </thead>
          <tbody>
            {row(t('expected_redemption'), base.mean, now.mean)}
            {row(t('p_above_par'), base.above, now.above)}
            {row(t('p5_redemption'), base.p5, now.p5)}
          </tbody>
        </table>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8, lineHeight: 1.5 }}>{t('whatif_hint')}</div>
      </div>
    </div>
  )
}
