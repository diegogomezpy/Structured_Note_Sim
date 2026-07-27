import { useI18n } from '../i18n/I18nProvider'
import { pct } from '../lib/format'
import type { SimSummary } from '../api/types'

interface Seg {
  key: string
  label: string
  frac: number
  color: string
  opacity: number
}

/** How 100% of paths resolve: autocalled at each period → held to maturity
    (redeemed at par) → knocked in. A stacked proportional bar + legend. */
export default function OutcomeWaterfall({ summary }: { summary: SimSummary }) {
  const { t } = useI18n()
  const byPeriod = summary.autocall_by_period ?? []
  const acPeriods = byPeriod
    .map((frac, i) => ({ period: i + 1 + (summary.period_offset ?? 0), frac }))
    .filter((s) => s.frac > 0.002)

  const matRedeemed = Math.max(0, (summary.prob_maturity ?? 0) - (summary.prob_knock_in_total ?? 0))
  const knockedIn = summary.prob_knock_in_total ?? 0

  const segs: Seg[] = [
    ...acPeriods.map((s, i) => ({
      key: `ac-${s.period}`,
      label: `${t('autocalled_at')} P${s.period}`,
      frac: s.frac,
      color: 'var(--accent)',
      opacity: 1 - 0.5 * (acPeriods.length > 1 ? i / (acPeriods.length - 1) : 0),
    })),
    { key: 'mat', label: t('redeemed_par'), frac: matRedeemed, color: 'var(--green)', opacity: 1 },
    { key: 'ki', label: t('knocked_in'), frac: knockedIn, color: 'var(--red)', opacity: 1 },
  ].filter((s) => s.frac > 0.001)

  return (
    <div>
      <div style={{ display: 'flex', height: 30, borderRadius: 8, overflow: 'hidden', background: 'var(--surface-2)' }}>
        {segs.map((s) => (
          <div
            key={s.key}
            title={`${s.label} — ${pct(s.frac, 1)}`}
            style={{
              flex: `${s.frac} 0 0`,
              background: s.color,
              opacity: s.opacity,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 11,
              fontWeight: 500,
              color: '#fff',
              transition: 'opacity 0.12s ease',
              cursor: 'default',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = '0.78')}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = String(s.opacity))}
          >
            {s.frac > 0.06 ? pct(s.frac, 0) : ''}
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px', marginTop: 12 }}>
        {segs.map((s) => (
          <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <span style={{ width: 9, height: 9, borderRadius: 3, background: s.color, opacity: s.opacity }} />
            <span style={{ color: 'var(--text-muted)' }}>{s.label}</span>
            <span className="mono" style={{ color: 'var(--text)' }}>{pct(s.frac, 1)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
