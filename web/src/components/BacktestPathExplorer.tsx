import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Icon from './Icon'
import { PathFan } from './PathExplorer'
import PathInspector from './PathInspector'
import type { BtRange, ExplorerData, NoteTerms } from '../api/types'

/** Historical-backtest path explorer — overlays every issue's worst-of trajectory
    (in note-relative time) coloured by outcome, reusing the Monte Carlo fan. */
export default function BacktestPathExplorer({ terms, range }: { terms: NoteTerms; range: BtRange }) {
  const { t } = useI18n()
  const [data, setData] = useState<ExplorerData | null>(null)
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [seed, setSeed] = useState(7)
  const sig = JSON.stringify({ terms, range })
  const inspectFetcher = useCallback(
    (body: Parameters<typeof api.backtestInspect>[1]) => api.backtestInspect(terms, body, range),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sig])

  useEffect(() => {
    let alive = true
    setStatus('loading')
    api.backtestPaths(terms, seed, 400, range).then((d) => { if (alive) { setData(d); setStatus(d.paths.length ? 'ok' : 'error') } })
      .catch(() => { if (alive) setStatus('error') })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, seed])

  if (status === 'loading') {
    return <Panel pad={40}><div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 14 }}><Icon name="spinner" size={18} /> {t('loading')}</div></Panel>
  }
  if (status === 'error' || !data) {
    return <Panel pad={40}><div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>{t('bt_explorer_empty')}</div></Panel>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <PathFan data={data} intro={t('bt_explorer_intro')}
               onResample={() => setSeed((s) => s + 1)}
               xLabel={t('chart_years_since_issue')}
               sampledNoun={t('bt_explorer_issues')} />
      <div style={{ borderTop: '1px solid var(--border)' }} />
      <PathInspector terms={terms} fetcher={inspectFetcher} />
    </div>
  )
}
