import AnimatedNumber from './AnimatedNumber'
import { InfoDot } from './Tooltip'
import { monthsNum } from '../lib/terms'
import { useI18n } from '../i18n/I18nProvider'
import { pct, num } from '../lib/format'
import type { SimSummary } from '../api/types'

interface Card {
  label: string
  value: number
  format: (n: number) => string
  unit?: string
  hint?: string
  tip: string
  tone: 'accent' | 'plain' | 'good' | 'bad'
}

/** Bare-number percentage formatter (the unit is rendered separately, smaller +
    muted — the register's split-unit rule). */
const pctNum = (dp: number) => (n: number) => num(n * 100, dp)

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
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
        {cards.map((c) => (
          <div key={c.label} className="card lift" style={{ padding: '18px 20px' }}>
            <div className="eyebrow" style={{ marginBottom: 12, display: 'flex', alignItems: 'center' }}>
              {c.label}<InfoDot title={c.label} body={c.tip} />
            </div>
            <div className="mono" style={{ fontSize: 33, fontWeight: 600, color: toneColor[c.tone], lineHeight: 0.95, letterSpacing: '-0.02em', display: 'flex', alignItems: 'baseline', gap: 1 }}>
              <AnimatedNumber value={c.value} format={c.format} animateOnMount />
              {c.unit && <span className="fig-unit" style={{ color: c.tone === 'plain' ? 'var(--text-faint)' : 'inherit', opacity: c.tone === 'plain' ? 1 : 0.7 }}>{c.unit}</span>}
            </div>
            {c.hint && <div className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 10 }}>{c.hint}</div>}
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

  // Secondary-market position: every return above is already measured on cost, so
  // say so on the headline figure and add the probability of actually losing money
  // — which is NOT the knock-in rate once you paid less (or more) than par.
  const cost = summary.cost_basis ?? 1
  const onCost = Math.abs(cost - 1) > 1e-9
  const costHint = onCost ? t('hint_on_cost', { v: pct(cost, 2) }) : undefined
  const lossCard: Card[] = onCost && summary.prob_loss != null
    ? [{ label: t('p_loss'), value: summary.prob_loss, format: pctNum(summary.prob_loss < 0.1 ? 2 : 1),
         unit: '%', tip: t('tip_p_loss'), tone: summary.prob_loss <= 0.15 ? 'good' : 'bad' }]
    : []

  // Participation notes never autocall / pay coupons — show redemption-distribution
  // metrics instead of the autocall/coupon tiles.
  if (summary.note_type === 'participation') {
    const belowPar = summary.prob_knock_in_total ?? 0
    const p5 = summary.p5_redemption ?? 1
    // A cliquet's "redemption" accrues over many resets, so the whole-note figure
    // (1 + summed income) misreads as a single payoff. Show the mean per-period
    // redemption instead — capital rolls at par, so it's 1 + mean period income.
    // period_income_mean is only present for cliquets, so it's the periodic signal
    // (the MC summary doesn't carry the participation_periodic flag itself).
    const periodic = (summary.participation_periodic ?? false) || (summary.period_income_mean?.length ?? 0) > 0
    // Divide by the periods actually PRICED, not the term sheet's total.
    // `expected_coupon` covers the priced window; on a held note that is the
    // remaining resets only, while `n_obs` stays the full tenor — so the mean was
    // scaled down by exactly the fraction of the note already elapsed (a note half
    // way through reported half the per-period redemption it earns).
    const pricedPeriods = Math.max(1, (summary.n_obs ?? 1) - (summary.period_offset ?? 0))
    const perPeriodRedemption = 1 + (summary.expected_coupon ?? 0) / pricedPeriods
    const redemptionCard: Card = periodic
      ? { label: t('expected_redemption_period'), value: perPeriodRedemption, format: pctNum(2), unit: '%', tip: t('tip_expected_redemption_period'), tone: 'accent' }
      : { label: t('expected_redemption'), value: summary.expected_redemption ?? summary.expected_nominal_payout ?? 1, format: pctNum(1), unit: '%', tip: t('tip_expected_redemption'), tone: 'accent' }
    const ret: Card[] = [
      redemptionCard,
      { label: t('expected_irr'), value: irr, format: pctNum(2), unit: '%', tip: t('tip_expected_irr'), hint: costHint, tone: irr >= 0 ? 'accent' : 'bad' },
      { label: t('expected_gain'), value: summary.expected_gain ?? 0, format: pctNum(2), unit: '%', tip: t('tip_expected_gain'), tone: 'plain' },
      ...(summary.up_capture != null ? [{ label: t('upside_capture'), value: summary.up_capture, format: pctNum(0), unit: '%', tip: t('tip_upside_capture'), tone: 'plain' as const }] : []),
    ]
    const cvar = summary.cvar5_redemption ?? p5
    const rsk: Card[] = [
      ...lossCard,
      { label: t('p_below_par'), value: belowPar, format: pctNum(belowPar < 0.1 ? 2 : 1), unit: '%', tip: t('tip_p_below_par'), tone: belowPar <= 0.15 ? 'good' : 'bad' },
      { label: t('p_above_par'), value: summary.prob_above_par ?? 0, format: pctNum(1), unit: '%', tip: t('tip_p_above_par'), tone: 'plain' },
      ...(summary.prob_at_cap != null ? [{ label: t('p_at_cap'), value: summary.prob_at_cap, format: pctNum(1), unit: '%', tip: t('tip_p_at_cap'), tone: 'plain' as const }] : []),
      ...(summary.prob_knocked_out != null ? [{ label: t('p_knocked_out'), value: summary.prob_knocked_out, format: pctNum(1), unit: '%', tip: t('tip_p_knocked_out'), tone: 'plain' as const }] : []),
      { label: t('p5_redemption'), value: p5, format: pctNum(1), unit: '%', tip: t('tip_p5_redemption'), tone: p5 >= 1 ? 'good' : 'bad' },
      { label: t('expected_shortfall'), value: cvar, format: pctNum(1), unit: '%', tip: t('tip_expected_shortfall'), tone: cvar >= 1 ? 'good' : 'bad' },
      ...(summary.dn_capture != null ? [{ label: t('downside_capture'), value: summary.dn_capture, format: pctNum(0), unit: '%', tip: t('tip_downside_capture'), tone: 'plain' as const }] : []),
    ]
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <Group title={t('hero_return')} cards={ret} />
        <Group title={t('hero_risk')} cards={rsk} />
      </div>
    )
  }

  const expected: Card[] = [
    { label: t('expected_irr'), value: irr, format: pctNum(2), unit: '%', tip: t('tip_expected_irr'),
      hint: costHint ?? `${t('vs_coupon')} ${pct(summary.coupon_pa, 1)}`, tone: irr >= 0 ? 'accent' : 'bad' },
    { label: t('expected_total_return'), value: summary.expected_total_return ?? 0, format: pctNum(2), unit: '%',
      tip: t('tip_expected_total_return'), tone: (summary.expected_total_return ?? 0) >= 0 ? 'plain' : 'bad' },
    { label: t('expected_coupon'), value: summary.expected_coupon ?? 0, format: pctNum(2), unit: '%',
      tip: t('tip_expected_coupon'), tone: 'plain' },
  ]

  const risk: Card[] = [
    { label: t('p_autocall'), value: summary.prob_autocall ?? 0, format: pctNum(2), unit: '%',
      hint: peakIdx >= 0 ? `${t('period')} P${peakIdx + 1 + (summary.period_offset ?? 0)}` : undefined,
      tip: t('tip_p_autocall'), tone: 'plain' },
    ...(summary.avg_time_to_autocall != null
      ? [{ label: t('avg_time_autocall'), value: monthsNum(summary.avg_time_to_autocall), format: (n: number) => num(n, 1), unit: 'mo',
          tip: t('tip_avg_time_autocall'), tone: 'plain' as const }]
      : []),
    { label: t('p_knock_in'), value: ki, format: pctNum(ki < 0.1 ? 2 : 1), unit: '%', tip: t('tip_p_knock_in'),
      tone: ki <= 0.15 ? 'good' : 'bad' },
    ...lossCard,
    { label: t('loss_given_ki'), value: summary.loss_given_knock_in ?? 0, format: pctNum(2), unit: '%',
      tip: t('tip_loss_given_ki'), tone: (summary.loss_given_knock_in ?? 0) >= 0 ? 'plain' : 'bad' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <Group title={t('hero_return')} cards={expected} />
      <Group title={t('hero_risk')} cards={risk} />
    </div>
  )
}
