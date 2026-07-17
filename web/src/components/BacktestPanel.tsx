import { useState, type ReactNode } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import Tabs from './Tabs'
import Icon from './Icon'
import TickerLogo from './TickerLogo'
import BacktestPathExplorer from './BacktestPathExplorer'
import AnimatedNumber from './AnimatedNumber'
import { InfoDot } from './Tooltip'
import { pct, pctSigned, num as numFmt } from '../lib/format'
import type { BacktestIssue, BacktestResult, BtRange, NoteTerms } from '../api/types'

type Kind = 'ac' | 'mat' | 'ki'
const KIND_COLOR: Record<Kind, string> = { ac: 'var(--accent)', mat: 'var(--green)', ki: 'var(--red)' }

function classify(i: BacktestIssue): Kind {
  if ((i.call_quarter ?? 0) > 0) return 'ac'
  return i.knock_in ? 'ki' : 'mat'
}

// Participation realised-redemption bands (client-derived so the colour is stable
// regardless of the translated label). cap = 1 + upside_cap, or null when uncapped.
type Band = 'loss' | 'par' | 'gain' | 'capped'
const BAND_COLOR: Record<Band, string> = {
  loss: 'var(--red)', par: 'var(--text-muted)', gain: 'var(--green)', capped: 'var(--accent)',
}
function partBand(i: BacktestIssue, cap: number | null): Band {
  const r = i.redemption ?? 1
  if (r < 1 - 1e-9) return 'loss'
  if (Math.abs(r - 1) <= 5e-3) return 'par'
  if (cap != null && r >= cap - 1e-6) return 'capped'
  return 'gain'
}

/** Backtest headline figure. Pass a fraction `num` (+`dp`) to count it up from 0
    with a split % unit (matching the MC hero); else a plain `value` string. */
function MiniStat({ label, value, num, dp = 2, tone, tip, unit = '%', scale = 100 }: { label: string; value?: string; num?: number | null | undefined; dp?: number; tone?: string; tip?: string; unit?: string; scale?: number }) {
  const animate = num != null && Number.isFinite(num)
  return (
    <div className="card lift" style={{ padding: '14px 16px' }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8, display: 'flex', alignItems: 'center' }}>
        {label}{tip && <InfoDot title={label} body={tip} />}
      </div>
      <div className="mono" style={{ fontSize: 24, fontWeight: 600, color: tone ?? 'var(--text)', lineHeight: 1, display: 'flex', alignItems: 'baseline', gap: 1 }}>
        {animate
          ? <><AnimatedNumber value={num! * scale} format={(n) => numFmt(n, dp)} animateOnMount /><i className="fig-unit" style={{ color: 'inherit', opacity: 0.7 }}>{unit}</i></>
          : value}
      </div>
    </div>
  )
}

function StatGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 10 }}>{title}</div>
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>{children}</div>
    </div>
  )
}

/** `sub` is owned by App so the rail's NavMenu can drive it; the local tab row
    below is only the phone fallback (the rail is hidden under 640px). */
export default function BacktestPanel({ result, terms, range, onApplyRange, sub, onSubChange }: {
  result: BacktestResult; terms: NoteTerms; range: BtRange; onApplyRange: (r: BtRange) => void
  sub: string; onSubChange: (s: string) => void
}) {
  const { t } = useI18n()
  const [start, setStart] = useState(range.start ?? '')
  const [end, setEnd] = useState(range.end ?? '')
  const { summary, issues, figures } = result
  const isPart = summary.note_type === 'participation'
  const periodic = !!summary.participation_periodic
  const cap = terms.upside_cap != null ? 1 + terms.upside_cap : null
  const bandLabel = (b: Band) => t(`bt_band_${b}` as const)
  const rangeDirty = (start || null) !== range.start || (end || null) !== range.end
  // ISO date strings compare lexically — a start after the end is invalid, so we
  // block the (doomed) request client-side rather than letting it return empty.
  const rangeInvalid = !!start && !!end && start > end
  const hasRange = !!(range.start || range.end)

  const nameToSym: Record<string, string> = {}
  for (const [sym, name] of Object.entries(terms.tickers ?? {})) nameToSym[name] = sym

  // The issue-window controls — rendered in BOTH the populated and the empty
  // state so a range that yields no issues never strands the user (the controls
  // used to vanish with the early-return, leaving no way back).
  const rangeBar = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>{t('bt_from')}</label>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
                 className={rangeInvalid ? 'field-invalid' : undefined} style={{ width: 'auto' }} />
        </div>
        <div>
          <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>{t('bt_to')}</label>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
                 className={rangeInvalid ? 'field-invalid' : undefined} style={{ width: 'auto' }} />
        </div>
        <button className="btn btn--primary" style={{ padding: '8px 14px' }} disabled={!rangeDirty || rangeInvalid}
                onClick={() => onApplyRange({ start: start || null, end: end || null })}>
          <Icon name="refresh" size={14} /> {t('bt_apply')}
        </button>
        {(hasRange || start || end) && (
          <button className="btn" style={{ padding: '8px 14px' }}
                  onClick={() => { setStart(''); setEnd(''); if (hasRange) onApplyRange({ start: null, end: null }) }}>{t('bt_clear')}</button>
        )}
      </div>
      {rangeInvalid && <div className="field-msg">{t('bt_range_invalid')}</div>}
    </div>
  )

  if (!issues.length) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('bt_intro')}</div>
        {rangeBar}
        <Panel pad={40}>
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 14, maxWidth: 460, margin: '0 auto', lineHeight: 1.6 }}>
            {t('bt_empty')}
            {hasRange && <div style={{ marginTop: 14 }}>
              <button className="btn" onClick={() => { setStart(''); setEnd(''); onApplyRange({ start: null, end: null }) }}>{t('bt_clear_range')}</button>
            </div>}
          </div>
        </Panel>
      </div>
    )
  }

  const label = (i: BacktestIssue) => {
    if (isPart) return bandLabel(partBand(i, cap))
    const k = classify(i)
    if (k === 'ac') return `${t('autocalled_at')} P${i.call_quarter}`
    return k === 'ki' ? t('knocked_in') : t('held_to_mat')
  }

  const n = issues.length
  let segs: { key: string; label: string; count: number; frac: number; color: string; opacity: number }[]
  if (isPart) {
    // Realised-redemption bands: gain / capped / par / loss.
    const bc: Record<Band, number> = { loss: 0, par: 0, gain: 0, capped: 0 }
    for (const i of issues) bc[partBand(i, cap)] += 1
    segs = (['gain', 'capped', 'par', 'loss'] as Band[]).map((b) => ({
      key: b, label: bandLabel(b), count: bc[b], frac: bc[b] / n, color: BAND_COLOR[b], opacity: 1,
    })).filter((s) => s.frac > 0)
  } else {
    // Break the autocalls out by period (matching the Monte-Carlo waterfall),
    // then held-to-maturity and knock-in.
    const periodCounts: Record<number, number> = {}
    let matCount = 0, kiCount = 0
    for (const i of issues) {
      const k = classify(i)
      if (k === 'ac') periodCounts[i.call_quarter ?? 0] = (periodCounts[i.call_quarter ?? 0] ?? 0) + 1
      else if (k === 'mat') matCount += 1
      else kiCount += 1
    }
    const acQs = Object.keys(periodCounts).map(Number).sort((a, b) => a - b)
    segs = [
      ...acQs.map((q, i) => ({
        key: `ac${q}`, label: `${t('autocalled_at')} P${q}`, count: periodCounts[q], frac: periodCounts[q] / n,
        color: 'var(--accent)', opacity: 1 - 0.5 * (acQs.length > 1 ? i / (acQs.length - 1) : 0),
      })),
      { key: 'mat', label: t('held_to_mat'), count: matCount, frac: matCount / n, color: 'var(--green)', opacity: 1 },
      { key: 'ki', label: t('knocked_in'), count: kiCount, frac: kiCount / n, color: 'var(--red)', opacity: 1 },
    ].filter((s) => s.frac > 0)
  }

  const rows = [...issues].reverse() // most recent first

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('bt_intro')}</div>

      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {t('bt_sample_caption', { n: summary.n_issues })}
        {summary.median_irr != null && <> · {t('bt_median_caption', { v: pct(summary.median_irr, 2) })}</>}
      </div>

      {/* Same 6-metric / two-group layout as the Monte-Carlo summary so the tabs
          read in parallel (returns row, then risk row). Median IRR sits in the
          caption above rather than as its own card. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {isPart ? (<>
          <StatGroup title={t('bt_realised')}>
            <MiniStat label={t('bt_mean_redemption')} num={summary.expected_redemption as number} dp={1} tip={t('bt_tip_mean_redemption')}
                      tone={(summary.expected_redemption as number ?? 1) >= 1 ? 'var(--accent-text)' : 'var(--red)'} />
            <MiniStat label={t('bt_mean_irr')} num={summary.mean_irr} dp={2} tip={t('bt_tip_mean_irr')}
                      tone={(summary.mean_irr ?? 0) >= 0 ? 'var(--text)' : 'var(--red)'} />
            {periodic
              ? <MiniStat label={t('bt_part_income')} num={summary.expected_coupon} dp={2} tip={t('bt_tip_part_income')} />
              : <MiniStat label={t('bt_best_redemption')} num={summary.best_redemption as number} dp={1} tip={t('bt_tip_best_redemption')} />}
          </StatGroup>
          <StatGroup title={t('hero_risk')}>
            <MiniStat label={t('bt_prob_above_par')} num={summary.prob_above_par as number} dp={1} tip={t('bt_tip_prob_above_par')}
                      tone={(summary.prob_above_par as number ?? 0) >= 0.5 ? 'var(--green)' : 'var(--text)'} />
            <MiniStat label={t('bt_prob_loss')} num={summary.prob_below_par as number} dp={1} tip={t('bt_tip_prob_loss')}
                      tone={(summary.prob_below_par as number ?? 0) <= 0.15 ? 'var(--green)' : 'var(--red)'} />
            <MiniStat label={t('bt_worst_redemption')} num={summary.worst_redemption as number} dp={1} tip={t('bt_tip_worst_redemption')}
                      tone={(summary.worst_redemption as number ?? 1) < 1 ? 'var(--red)' : 'var(--text)'} />
            <MiniStat label={t('bt_cvar')} num={summary.cvar5_redemption as number} dp={1} tip={t('bt_tip_cvar')}
                      tone={(summary.cvar5_redemption as number ?? 1) < 1 ? 'var(--red)' : 'var(--text)'} />
          </StatGroup>
        </>) : (<>
          <StatGroup title={t('bt_realised')}>
            <MiniStat label={t('bt_mean_irr')} num={summary.mean_irr} dp={2} tip={t('bt_tip_mean_irr')}
                      tone={(summary.mean_irr ?? 0) >= 0 ? 'var(--accent-text)' : 'var(--red)'} />
            <MiniStat label={t('bt_total_return')} num={summary.expected_total_return} dp={2} tip={t('bt_tip_total_return')}
                      tone={(summary.expected_total_return ?? 0) >= 0 ? 'var(--text)' : 'var(--red)'} />
            <MiniStat label={t('bt_coupon_income')} num={summary.expected_coupon} dp={2} tip={t('bt_tip_coupon')} />
          </StatGroup>
          <StatGroup title={t('hero_risk')}>
            <MiniStat label={t('bt_called_rate')} num={summary.prob_called} dp={1} tip={t('bt_tip_called')} />
            <MiniStat label={t('avg_time_autocall')} num={summary.avg_time_to_autocall} value="—" dp={2}
                      unit="y" scale={1} tip={t('tip_avg_time_autocall')} />
            <MiniStat label={t('bt_ki_rate')} num={summary.prob_knock_in} dp={1} tip={t('bt_tip_ki')}
                      tone={(summary.prob_knock_in ?? 0) <= 0.15 ? 'var(--green)' : 'var(--red)'} />
            <MiniStat label={t('loss_given_ki')}
                      num={(summary.prob_knock_in ?? 0) > 0 ? summary.loss_given_knock_in : null} value="—" dp={2}
                      tip={t('bt_tip_lgki')}
                      tone={(summary.loss_given_knock_in ?? 0) < 0 ? 'var(--red)' : 'var(--text)'} />
          </StatGroup>
        </>)}
      </div>

      {rangeBar}

      <div className="nav-mobile-only">
        <Tabs tabs={[{ id: 'outcomes', label: t('bt_sub_outcomes') }, { id: 'prices', label: t('bt_sub_prices') }, { id: 'sample', label: t('bt_sub_sample') }, { id: 'explorer', label: t('bt_sub_explorer') }]} active={sub} onChange={onSubChange} />
      </div>

      {sub === 'outcomes' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="stagger">
      <Panel title={t('bt_outcomes')} right={`${n} ${t('bt_issues').toLowerCase()}`}>
        <div style={{ display: 'flex', height: 28, borderRadius: 8, overflow: 'hidden', background: 'var(--surface-2)' }}>
          {segs.map((s) => (
            <div key={s.key} title={`${s.label} — ${s.count} · ${pct(s.frac, 1)}`}
                 style={{ flex: `${s.frac} 0 0`, background: s.color, opacity: s.opacity, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 500, color: '#fff' }}>
              {s.frac > 0.07 ? pct(s.frac, 0) : ''}
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px', marginTop: 12 }}>
          {segs.map((s) => (
            <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <span style={{ width: 9, height: 9, borderRadius: 3, background: s.color, opacity: s.opacity }} />
              <span style={{ color: 'var(--text-muted)' }}>{s.label}</span>
              <span className="mono" style={{ color: 'var(--text)' }}>{s.count} · {pct(s.frac, 0)}</span>
            </div>
          ))}
        </div>
      </Panel>

      {isPart && figures?.redemption_dist && (
        <Panel title={t('redemption_distribution')} right={`${n} ${t('bt_issues').toLowerCase()}`} pad={14}>
          <div style={{ height: 300 }}><Figure fig={figures.redemption_dist} name="bt_redemption_dist" /></div>
        </Panel>
      )}

      {figures && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 18 }}>
          <Panel title={t('bt_worst_pie')} pad={14}><div style={{ height: 300 }}><Figure fig={figures.worst_asset_pie} name="worst_asset_pie" /></div></Panel>
          <Panel title={isPart ? t('bt_redemption_scatter') : t('bt_irr_scatter')} pad={14}><div style={{ height: 300 }}><Figure fig={figures.irr_scatter} name="backtest_irr_scatter" /></div></Panel>
        </div>
      )}

      <Panel title={t('bt_table')} pad={0}>
        <div style={{ maxHeight: 420, overflow: 'auto' }}>
          <table className="ledger">
            <thead>
              <tr style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
                {(isPart
                  ? [t('col_date'), t('col_outcome'), t('col_worst'), t('col_redemption'), t('col_irr')]
                  : [t('col_date'), t('col_outcome'), t('col_worst'), t('col_worst_perf'), t('col_irr')]).map((h, i) => (
                  <th key={h} className={i >= 3 ? 'num' : undefined}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((i, idx) => {
                const dot = isPart ? BAND_COLOR[partBand(i, cap)] : KIND_COLOR[classify(i)]
                return (
                  <tr key={i.issue_date + idx}>
                    <td style={{ color: 'var(--text-muted)' }}>{i.issue_date}</td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: dot }} />
                        {label(i)}
                      </span>
                    </td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <TickerLogo symbol={nameToSym[i.worst_asset] ?? i.worst_asset} name={i.worst_asset} size={16} />
                        {i.worst_asset}
                      </span>
                    </td>
                    {isPart
                      ? <td className="num" style={{ color: (i.redemption ?? 1) < 1 ? 'var(--red)' : 'var(--text)' }}>{pct(i.redemption, 1)}</td>
                      : <td className="num" style={{ color: (i.worst_perf ?? 1) < (terms.knock_in_barrier) ? 'var(--red)' : 'var(--text)' }}>{pct(i.worst_perf, 0)}</td>}
                    <td className="num" style={{ color: (i.irr ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{pctSigned(i.irr, 1)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
        </div>
      )}

      {sub === 'prices' && figures && (
        <Panel title={t('bt_price_history')} pad={14} className="fade-up">
          <div style={{ height: 440 }}><Figure fig={figures.prices} name="price_history" /></div>
        </Panel>
      )}

      {sub === 'sample' && <div className="fade-up"><BacktestPathExplorer terms={terms} range={range} view="sample" /></div>}
      {sub === 'explorer' && <div className="fade-up"><BacktestPathExplorer terms={terms} range={range} view="explorer" /></div>}
    </div>
  )
}
