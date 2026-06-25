import AnimatedNumber from './AnimatedNumber'
import { useI18n } from '../i18n/I18nProvider'
import { pct } from '../lib/format'
import type { SimSummary } from '../api/types'

interface Card {
  label: string
  value: number
  format: (n: number) => string
  hint?: string
  tip: string
  tone: 'accent' | 'plain' | 'good' | 'bad'
}

const toneColor: Record<Card['tone'], string> = {
  accent: 'var(--accent-text)',
  plain: 'var(--text)',
  good: 'var(--green)',
  bad: 'var(--red)',
}

function Group({ title, cards }: { title: string; cards: Card[] }) {
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 10 }}>{title}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
        {cards.map((c) => (
          <div key={c.label} className="card fade-up" title={c.tip} style={{ padding: '18px 20px', cursor: 'help' }}>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5 }}>
              {c.label}<span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>ⓘ</span>
            </div>
            <div className="mono" style={{ fontSize: 34, fontWeight: 600, color: toneColor[c.tone], lineHeight: 0.95, letterSpacing: '-0.02em' }}>
              <AnimatedNumber value={c.value} format={c.format} />
            </div>
            {c.hint && <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 10 }}>{c.hint}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function HeroMetrics({ summary }: { summary: SimSummary }) {
  const { t } = useI18n()

  const byPeriod = summary.autocall_by_period ?? []
  const peakIdx = byPeriod.length ? byPeriod.reduce((best, v, i) => (v > byPeriod[best] ? i : best), 0) : -1
  const irr = summary.expected_irr ?? 0
  const ki = summary.prob_knock_in_total ?? 0

  const expected: Card[] = [
    { label: t('expected_irr'), value: irr, format: (n) => pct(n, 2), tip: t('tip_expected_irr'),
      hint: `${t('vs_coupon')} ${pct(summary.coupon_pa, 1)}`, tone: irr >= 0 ? 'accent' : 'bad' },
    { label: t('expected_total_return'), value: summary.expected_total_return ?? 0, format: (n) => pct(n, 2),
      tip: t('tip_expected_total_return'), tone: (summary.expected_total_return ?? 0) >= 0 ? 'plain' : 'bad' },
    { label: t('expected_coupon'), value: summary.expected_coupon ?? 0, format: (n) => pct(n, 2),
      tip: t('tip_expected_coupon'), tone: 'plain' },
  ]

  const risk: Card[] = [
    { label: t('p_autocall'), value: summary.prob_autocall ?? 0, format: (n) => pct(n, 2),
      hint: peakIdx >= 0 ? `${t('period')} P${peakIdx + 1}` : undefined, tip: t('tip_p_autocall'), tone: 'plain' },
    { label: t('p_knock_in'), value: ki, format: (n) => pct(n, ki < 0.1 ? 2 : 1), tip: t('tip_p_knock_in'),
      tone: ki <= 0.15 ? 'good' : 'bad' },
    { label: t('loss_given_ki'), value: summary.loss_given_knock_in ?? 0, format: (n) => pct(n, 2),
      tip: t('tip_loss_given_ki'), tone: (summary.loss_given_knock_in ?? 0) >= 0 ? 'plain' : 'bad' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <Group title={t('hero_return')} cards={expected} />
      <Group title={t('hero_risk')} cards={risk} />
    </div>
  )
}
