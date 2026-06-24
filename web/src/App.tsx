import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api/client'
import type { ConfigMeta, NoteTerms, SimResult } from './api/types'
import { useI18n } from './i18n/I18nProvider'
import Header from './components/Header'
import SetupRail, { type RunOpts } from './components/SetupRail'
import NoteTimeline from './components/NoteTimeline'
import Panel from './components/Panel'
import Tabs from './components/Tabs'
import RunProgress from './components/RunProgress'
import MonteCarloPanel from './components/MonteCarloPanel'
import BrandMark from './components/BrandMark'
import Icon from './components/Icon'

type Status = 'idle' | 'running' | 'error'

/** Signature of the exact inputs a run depends on, so we can flag a displayed
    result as stale once the user edits terms or run options after running. */
const sigOf = (terms: NoteTerms, opts: RunOpts) =>
  JSON.stringify({ terms, n: opts.n_paths, e: opts.engine })

export default function App() {
  const { t, lang } = useI18n()
  const [configs, setConfigs] = useState<ConfigMeta[]>([])
  const [configFile, setConfigFile] = useState('')
  const [terms, setTerms] = useState<NoteTerms | null>(null)
  const [opts, setOpts] = useState<RunOpts>({ n_paths: 10000, engine: 'numpy' })
  const [cppAvailable, setCppAvailable] = useState(false)
  const [result, setResult] = useState<SimResult | null>(null)
  const [runSig, setRunSig] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [tab, setTab] = useState('mc')

  // Bootstrap: engine availability + config list + default term sheet.
  useEffect(() => {
    api.health().then((h) => setCppAvailable(h.cpp_engine)).catch(() => {})
    api.configs().then((cs) => {
      setConfigs(cs)
      if (cs.length) loadConfig(cs[0].file)
    }).catch((e) => setErrorMsg(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadConfig = useCallback(async (file: string) => {
    setConfigFile(file)
    const tm = await api.config(file)
    setTerms(tm)
    setResult(null)
    setRunSig('')
  }, [])

  const run = useCallback(async () => {
    if (!terms) return
    setStatus('running')
    setErrorMsg('')
    try {
      const res = await api.simulate({ terms, n_paths: opts.n_paths, engine: opts.engine, lang })
      setResult(res)
      setRunSig(sigOf(terms, opts))
      setTab('mc')
      setStatus('idle')
    } catch (e) {
      setErrorMsg(String(e instanceof Error ? e.message : e))
      setStatus('error')
    }
  }, [terms, opts, lang])

  const stale = useMemo(
    () => !!result && !!runSig && !!terms && sigOf(terms, opts) !== runSig,
    [result, runSig, terms, opts],
  )

  const runMeta = result
    ? { engine: result.summary.engine, nPaths: result.summary.n_paths, stale }
    : null

  const tabs = [
    { id: 'mc', label: t('tab_mc') },
    { id: 'bt', label: t('tab_backtest') },
    { id: 'live', label: t('tab_live') },
    { id: 'report', label: <span><Icon name="chart" size={13} /> {t('tab_report')}</span> },
  ]

  return (
    <div style={{ minHeight: '100%', display: 'flex', flexDirection: 'column' }}>
      <Header terms={terms} run={runMeta} />

      <div className="app-layout">
        <aside className="app-rail">
          <Panel title={t('setup_heading')}>
            {terms ? (
              <SetupRail
                terms={terms} onChange={setTerms}
                configs={configs} configFile={configFile} onSelectConfig={loadConfig}
                opts={opts} onOptsChange={setOpts}
                cppAvailable={cppAvailable}
                running={status === 'running'} stale={stale} onRun={run}
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[...Array(6)].map((_, i) => <div key={i} className="skeleton" style={{ height: 34 }} />)}
              </div>
            )}
          </Panel>
        </aside>

        <main style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
          {terms && (
            <Panel title={t('note_structure')} right={t('live_updates')}>
              <NoteTimeline terms={terms} />
            </Panel>
          )}

          <Tabs tabs={tabs} active={tab} onChange={setTab} />

          {tab === 'mc' && (
            <>
              {stale && result && status !== 'running' && (
                <div role="status" style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px',
                  background: 'var(--amber-weak)', border: '1px solid var(--amber)',
                  borderRadius: 11, fontSize: 13, color: 'var(--text)',
                }}>
                  <Icon name="refresh" size={16} />
                  <span style={{ flex: 1 }}>{t('stale_banner')}</span>
                  <button className="btn" onClick={run} style={{ padding: '6px 12px' }}>{t('rerun')}</button>
                </div>
              )}
              {status === 'running' && <Panel><RunProgress /></Panel>}
              {status === 'error' && (
                <Panel>
                  <div style={{ color: 'var(--red)', fontSize: 13 }}>
                    <strong>{t('error')}.</strong> {errorMsg}
                  </div>
                </Panel>
              )}
              {status !== 'running' && result && terms && <MonteCarloPanel result={result} terms={terms} />}
              {status === 'idle' && !result && (
                <Panel pad={48}>
                  <div style={{ textAlign: 'center', maxWidth: 440, margin: '0 auto' }}>
                    <div style={{
                      width: 52, height: 52, borderRadius: 14, margin: '0 auto 16px',
                      background: 'var(--accent-weak)', color: 'var(--accent-text)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}><BrandMark size={28} /></div>
                    <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 8 }}>{t('no_run_title')}</div>
                    <div style={{ fontSize: 13.5, color: 'var(--text-muted)', lineHeight: 1.65 }}>{t('no_run_body')}</div>
                  </div>
                </Panel>
              )}
            </>
          )}

          {tab !== 'mc' && (
            <Panel pad={48}>
              <div style={{ textAlign: 'center', color: 'var(--text-faint)', fontSize: 14 }}>{t('coming_soon')}</div>
            </Panel>
          )}
        </main>
      </div>
    </div>
  )
}
