import { useCallback, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import HeroMetrics from './HeroMetrics'
import PathExplorer from './PathExplorer'
import PathInspector from './PathInspector'
import { AutocallByPeriodTable, CalibrationTable } from './MCTables'
import Tabs from './Tabs'
import TickerLogo from './TickerLogo'
import type { NoteTerms, SimResult } from '../api/types'

const CHART_H = 320

export default function MonteCarloPanel({ result, terms }: { result: SimResult; terms: NoteTerms }) {
  const { t } = useI18n()
  const { summary, figures } = result
  const [sub, setSub] = useState('summary')
  const inspectFetcher = useCallback(
    (body: Parameters<typeof api.inspectRun>[1]) => api.inspectRun(result.run_id, body),
    [result.run_id])

  // Invert tickers ({sym: name}) so each fan's display name resolves to a logo.
  const nameToSym: Record<string, string> = {}
  for (const [sym, name] of Object.entries(terms.tickers ?? {})) nameToSym[name] = sym

  const subTabs = [
    { id: 'summary', label: t('sub_summary') },
    { id: 'fans', label: t('sub_fans') },
    { id: 'sample', label: t('sub_sample') },
    { id: 'explorer', label: t('sub_explorer') },
    { id: 'correlation', label: t('sub_correlation') },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <HeroMetrics summary={summary} />

      <div style={{ marginTop: 2 }}>
        <Tabs tabs={subTabs} active={sub} onChange={setSub} />
      </div>

      {sub === 'summary' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="stagger">
          <Panel title={t('outcomes')} right={`${summary.n_paths.toLocaleString()} ${t('paths').toLowerCase()} · ${summary.engine}`} pad={14}>
            <div style={{ height: 210 }}><Figure fig={figures.outcome} name="outcome_breakdown" /></div>
          </Panel>
          <Panel title={t('irr_distribution')} pad={14}>
            <div style={{ height: CHART_H }}><Figure fig={figures.irr_dist} name="irr_distribution" /></div>
          </Panel>
          <Panel title={t('autocall_by_period_h')} pad={0}>
            <AutocallByPeriodTable summary={summary} autocallStart={terms.autocall_start_period} />
          </Panel>
        </div>
      )}

      {sub === 'fans' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="stagger">
          <Panel title={t('worst_of_fan')} pad={14}>
            <div style={{ height: CHART_H }}><Figure fig={figures.wof_fan} name="worst_of_fan" /></div>
          </Panel>
          {figures.asset_fans.length > 0 && (
            <Panel title={t('per_asset')} pad={14}>
              {/* Stacked full-width (one below the other) so 3+ underlyings don't
                  squish — each fan reads like the worst-of fan above. No tinted
                  card behind each fan (that belongs in the PDF, not here); a thin
                  divider separates them on the panel surface. */}
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {figures.asset_fans.map((a, i) => (
                  <div key={a.name} style={{ paddingTop: i === 0 ? 0 : 16, marginTop: i === 0 ? 0 : 16, borderTop: i === 0 ? 'none' : '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <TickerLogo symbol={nameToSym[a.name] ?? a.name} name={a.name} size={20} />
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{a.name}</span>
                    </div>
                    <div style={{ height: CHART_H }}><Figure fig={a.fig} name={`${a.name}_fan`} /></div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      )}

      {sub === 'sample' && (
        <div className="fade-up">
          <PathExplorer runId={result.run_id} total={summary.n_paths} />
        </div>
      )}

      {sub === 'explorer' && (
        <div className="fade-up">
          <PathInspector terms={terms} fetcher={inspectFetcher} />
        </div>
      )}

      {sub === 'correlation' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="stagger">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 18 }}>
            <Panel title={t('corr_input')} pad={14}>
              <div style={{ height: 360 }}><Figure fig={figures.corr_input} name="corr_input" /></div>
            </Panel>
            <Panel title={t('corr_realized')} pad={14}>
              <div style={{ height: 360 }}><Figure fig={figures.corr_realized} name="corr_realized" /></div>
            </Panel>
            <Panel title={t('corr_difference')} pad={14}>
              <div style={{ height: 360 }}><Figure fig={figures.corr_diff} name="corr_difference" /></div>
            </Panel>
          </div>
          <Panel title={t('calibration_h')} pad={0}>
            <CalibrationTable summary={summary} nameToSym={nameToSym} />
          </Panel>
        </div>
      )}
    </div>
  )
}
