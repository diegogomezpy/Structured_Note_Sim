import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import HeroMetrics from './HeroMetrics'
import OutcomeWaterfall from './OutcomeWaterfall'
import Tabs from './Tabs'
import TickerLogo from './TickerLogo'
import type { NoteTerms, SimResult } from '../api/types'

const CHART_H = 320

export default function MonteCarloPanel({ result, terms }: { result: SimResult; terms: NoteTerms }) {
  const { t } = useI18n()
  const { summary, figures } = result
  const [sub, setSub] = useState('summary')

  // Invert tickers ({sym: name}) so each fan's display name resolves to a logo.
  const nameToSym: Record<string, string> = {}
  for (const [sym, name] of Object.entries(terms.tickers ?? {})) nameToSym[name] = sym

  const subTabs = [
    { id: 'summary', label: t('sub_summary') },
    { id: 'fans', label: t('sub_fans') },
    { id: 'correlation', label: t('sub_correlation') },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <HeroMetrics summary={summary} />

      <div style={{ marginTop: 2 }}>
        <Tabs tabs={subTabs} active={sub} onChange={setSub} />
      </div>

      {sub === 'summary' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
          <Panel title={t('outcomes')} right={`${summary.n_paths.toLocaleString()} ${t('paths').toLowerCase()} · ${summary.engine}`}>
            <OutcomeWaterfall summary={summary} />
          </Panel>
          <Panel title={t('irr_distribution')} pad={14}>
            <div style={{ height: CHART_H }}><Figure fig={figures.irr_dist} /></div>
          </Panel>
        </div>
      )}

      {sub === 'fans' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
          <Panel title={t('worst_of_fan')} pad={14}>
            <div style={{ height: CHART_H }}><Figure fig={figures.wof_fan} /></div>
          </Panel>
          {figures.asset_fans.length > 0 && (
            <Panel title={t('per_asset')} pad={14}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
                {figures.asset_fans.map((a) => (
                  <div key={a.name} style={{ background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <TickerLogo symbol={nameToSym[a.name] ?? a.name} name={a.name} size={20} />
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{a.name}</span>
                    </div>
                    <div style={{ height: 240 }}><Figure fig={a.fig} /></div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      )}

      {sub === 'correlation' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 18 }} className="fade-up">
          <Panel title={`${t('correlation')} · ${t('corr_input')}`} pad={14}>
            <div style={{ height: 300 }}><Figure fig={figures.corr_input} /></div>
          </Panel>
          <Panel title={`${t('correlation')} · ${t('corr_realized')}`} pad={14}>
            <div style={{ height: 300 }}><Figure fig={figures.corr_realized} /></div>
          </Panel>
        </div>
      )}
    </div>
  )
}
