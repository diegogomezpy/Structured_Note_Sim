import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import Tabs from './Tabs'
import TickerLogo from './TickerLogo'
import BacktestPathExplorer from './BacktestPathExplorer'
import { pct, pctSigned } from '../lib/format'
import type { BacktestIssue, BacktestResult, NoteTerms } from '../api/types'

type Kind = 'ac' | 'mat' | 'ki'
const KIND_COLOR: Record<Kind, string> = { ac: 'var(--accent)', mat: 'var(--green)', ki: 'var(--red)' }

function classify(i: BacktestIssue): Kind {
  if (i.call_quarter > 0) return 'ac'
  return i.knock_in ? 'ki' : 'mat'
}

function MiniStat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="card" style={{ padding: '14px 16px' }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>{label}</div>
      <div className="mono" style={{ fontSize: 24, fontWeight: 600, color: tone ?? 'var(--text)', lineHeight: 1 }}>{value}</div>
    </div>
  )
}

export default function BacktestPanel({ result, terms }: { result: BacktestResult; terms: NoteTerms }) {
  const { t } = useI18n()
  const [sub, setSub] = useState('outcomes')
  const { summary, issues, figures } = result

  const nameToSym: Record<string, string> = {}
  for (const [sym, name] of Object.entries(terms.tickers ?? {})) nameToSym[name] = sym

  if (!issues.length) {
    return <Panel pad={40}><div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>{t('bt_empty')}</div></Panel>
  }

  const label = (i: BacktestIssue) => {
    const k = classify(i)
    if (k === 'ac') return `${t('autocalled_at')} P${i.call_quarter}`
    return k === 'ki' ? t('knocked_in') : t('held_to_mat')
  }

  // Break the autocalls out by period (matching the Monte-Carlo waterfall),
  // then held-to-maturity and knock-in.
  const n = issues.length
  const periodCounts: Record<number, number> = {}
  let matCount = 0, kiCount = 0
  for (const i of issues) {
    const k = classify(i)
    if (k === 'ac') periodCounts[i.call_quarter] = (periodCounts[i.call_quarter] ?? 0) + 1
    else if (k === 'mat') matCount += 1
    else kiCount += 1
  }
  const acQs = Object.keys(periodCounts).map(Number).sort((a, b) => a - b)
  const segs = [
    ...acQs.map((q, i) => ({
      key: `ac${q}`, label: `${t('autocalled_at')} P${q}`, count: periodCounts[q], frac: periodCounts[q] / n,
      color: 'var(--accent)', opacity: 1 - 0.5 * (acQs.length > 1 ? i / (acQs.length - 1) : 0),
    })),
    { key: 'mat', label: t('held_to_mat'), count: matCount, frac: matCount / n, color: 'var(--green)', opacity: 1 },
    { key: 'ki', label: t('knocked_in'), count: kiCount, frac: kiCount / n, color: 'var(--red)', opacity: 1 },
  ].filter((s) => s.frac > 0)

  const rows = [...issues].reverse() // most recent first

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('bt_intro')}</div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14 }}>
        <MiniStat label={t('bt_issues')} value={String(summary.n_issues)} />
        <MiniStat label={t('bt_mean_irr')} value={pct(summary.mean_irr, 1)}
                  tone={(summary.mean_irr ?? 0) >= 0 ? 'var(--accent-text)' : 'var(--red)'} />
        <MiniStat label={t('bt_called_rate')} value={pct(summary.prob_called, 0)} />
        <MiniStat label={t('bt_ki_rate')} value={pct(summary.prob_knock_in, 0)}
                  tone={(summary.prob_knock_in ?? 0) <= 0.15 ? 'var(--green)' : 'var(--red)'} />
      </div>

      <Tabs tabs={[{ id: 'outcomes', label: t('bt_sub_outcomes') }, { id: 'prices', label: t('bt_sub_prices') }, { id: 'explorer', label: t('bt_sub_explorer') }]} active={sub} onChange={setSub} />

      {sub === 'outcomes' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
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

      {figures && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 18 }}>
          <Panel title={t('bt_worst_pie')} pad={14}><div style={{ height: 300 }}><Figure fig={figures.worst_asset_pie} /></div></Panel>
          <Panel title={t('bt_irr_scatter')} pad={14}><div style={{ height: 300 }}><Figure fig={figures.irr_scatter} /></div></Panel>
        </div>
      )}

      <Panel title={t('bt_table')} pad={0}>
        <div style={{ maxHeight: 420, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
                {[t('col_date'), t('col_outcome'), t('col_worst'), t('col_worst_perf'), t('col_irr')].map((h, i) => (
                  <th key={h} style={{ textAlign: i >= 3 ? 'right' : 'left', padding: '10px 16px', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((i, idx) => {
                const k = classify(i)
                return (
                  <tr key={i.issue_date + idx} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="mono" style={{ padding: '9px 16px', color: 'var(--text-muted)' }}>{i.issue_date}</td>
                    <td style={{ padding: '9px 16px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: KIND_COLOR[k] }} />
                        {label(i)}
                      </span>
                    </td>
                    <td style={{ padding: '9px 16px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <TickerLogo symbol={nameToSym[i.worst_asset] ?? i.worst_asset} name={i.worst_asset} size={16} />
                        {i.worst_asset}
                      </span>
                    </td>
                    <td className="mono" style={{ padding: '9px 16px', textAlign: 'right', color: (i.worst_perf ?? 1) < (terms.knock_in_barrier) ? 'var(--red)' : 'var(--text)' }}>{pct(i.worst_perf, 0)}</td>
                    <td className="mono" style={{ padding: '9px 16px', textAlign: 'right', color: (i.irr ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{pctSigned(i.irr, 1)}</td>
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
          <div style={{ height: 440 }}><Figure fig={figures.prices} /></div>
        </Panel>
      )}

      {sub === 'explorer' && <BacktestPathExplorer terms={terms} />}
    </div>
  )
}
