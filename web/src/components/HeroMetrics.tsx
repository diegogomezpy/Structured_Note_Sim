import AnimatedNumber from './AnimatedNumber'
import { useI18n } from '../i18n/I18nProvider'
import { pct, per100 } from '../lib/format'
import type { SimSummary } from '../api/types'

interface Card {
  label: string
  value: number
  format: (n: number) => string
  hint: string
  tone: 'accent' | 'plain' | 'good' | 'bad'
}

const toneColor: Record<Card['tone'], string> = {
  accent: 'var(--accent-text)',
  plain: 'var(--text)',
  good: 'var(--green)',
  bad: 'var(--red)',
}

export default function HeroMetrics({ summary }: { summary: SimSummary }) {
  const { t } = useI18n()

  const byPeriod = summary.autocall_by_period ?? []
  const peakIdx = byPeriod.length
    ? byPeriod.reduce((best, v, i) => (v > byPeriod[best] ? i : best), 0)
    : -1

  const irr = summary.expected_irr ?? 0
  const ki = summary.prob_knock_in_total ?? 0

  const cards: Card[] = [
    {
      label: t('expected_irr'),
      value: irr,
      format: (n) => pct(n, 1),
      hint: `${t('vs_coupon')} ${pct(summary.coupon_pa, 1)}`,
      tone: irr >= 0 ? 'accent' : 'bad',
    },
    {
      label: t('p_autocall'),
      value: summary.prob_autocall ?? 0,
      format: (n) => pct(n, 0),
      hint: peakIdx >= 0 ? `${t('period')} P${peakIdx + 1}` : '—',
      tone: 'plain',
    },
    {
      label: t('p_knock_in'),
      value: ki,
      format: (n) => pct(n, ki < 0.1 ? 2 : 1),
      hint: `${t('knocked_in')} ${pct(summary.loss_given_knock_in, 0)}`,
      tone: ki <= 0.15 ? 'good' : 'bad',
    },
    {
      label: t('exp_payout'),
      value: summary.expected_nominal_payout ?? 0,
      format: (n) => per100(n, 1),
      hint: t('per_100'),
      tone: 'plain',
    },
  ]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
      {cards.map((c) => (
        <div key={c.label} className="card fade-up" style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12 }}>
            {c.label}
          </div>
          <div className="mono" style={{ fontSize: 38, fontWeight: 600, color: toneColor[c.tone], lineHeight: 0.95, letterSpacing: '-0.02em' }}>
            <AnimatedNumber value={c.value} format={c.format} />
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 10 }}>{c.hint}</div>
        </div>
      ))}
    </div>
  )
}
