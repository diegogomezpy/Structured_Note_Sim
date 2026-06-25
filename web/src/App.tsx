import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api/client'
import { blankNote } from './lib/blankNote'
import type { BacktestResult, BtRange, ConfigMeta, LiveResult, NoteTerms, SimResult } from './api/types'
import { useI18n } from './i18n/I18nProvider'
import Header from './components/Header'
import SetupRail, { type RunOpts } from './components/SetupRail'
import NoteTimeline from './components/NoteTimeline'
import NoteDescription from './components/NoteDescription'
import ObservationSchedule from './components/ObservationSchedule'
import IssuerCard from './components/IssuerCard'
import UnderlyingCards from './components/UnderlyingCards'
import Panel from './components/Panel'
import Tabs from './components/Tabs'
import RunProgress from './components/RunProgress'
import MonteCarloPanel from './components/MonteCarloPanel'
import BacktestPanel from './components/BacktestPanel'
import LivePanel from './components/LivePanel'
import ReportPanel from './components/ReportPanel'
import SettingsOverlay from './components/SettingsOverlay'
import BrandMark from './components/BrandMark'
import Icon from './components/Icon'

type Status = 'idle' | 'running' | 'error'

/** Signature of the exact inputs a run depends on, so we can flag a displayed
    result as stale once the user edits terms or run options after running. */
const sigOf = (terms: NoteTerms, opts: RunOpts) =>
  JSON.stringify({ terms, n: opts.n_paths, e: opts.engine, s: opts.seed, c: opts.calib_years })

export default function App() {
  const { t, lang } = useI18n()
  const [configs, setConfigs] = useState<ConfigMeta[]>([])
  const [configFile, setConfigFile] = useState('')
  const [terms, setTerms] = useState<NoteTerms | null>(null)
  const [opts, setOpts] = useState<RunOpts>({ n_paths: 10000, engine: 'numpy', seed: 42, calib_years: 5 })
  const [cppAvailable, setCppAvailable] = useState(false)
  const [result, setResult] = useState<SimResult | null>(null)
  const [runSig, setRunSig] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [tab, setTab] = useState('mc')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [diagramOpen, setDiagramOpen] = useState(true)
  // Backtest is fetched lazily on first open of its tab (only depends on terms).
  const [btResult, setBtResult] = useState<BacktestResult | null>(null)
  const [btSig, setBtSig] = useState('')
  const [btStatus, setBtStatus] = useState<Status>('idle')
  const [btError, setBtError] = useState('')
  const [btRange, setBtRange] = useState<BtRange>({ start: null, end: null })
  // Current-performance (live) is likewise fetched lazily, keyed on terms.
  const [liveResult, setLiveResult] = useState<LiveResult | null>(null)
  const [liveSig, setLiveSig] = useState('')
  const [liveStatus, setLiveStatus] = useState<Status>('idle')
  const [liveError, setLiveError] = useState('')

  // Bootstrap: engine availability + config list. Start on a blank note rather
  // than auto-loading a bundled term sheet.
  useEffect(() => {
    const checkHealth = (retry = true) =>
      api.health()
        .then((h) => { setCppAvailable(h.cpp_engine); if (!h.cpp_engine && retry) setTimeout(() => checkHealth(false), 1500) })
        .catch(() => { if (retry) setTimeout(() => checkHealth(false), 1500) })
    checkHealth()
    api.configs().then(setConfigs).catch((e) => setErrorMsg(String(e)))
    setTerms(blankNote())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadConfig = useCallback(async (file: string) => {
    setConfigFile(file)
    // Empty selection = the blank-note starting point (no backend fetch).
    const tm = file ? await api.config(file) : blankNote()
    setTerms(tm)
    setResult(null)
    setRunSig('')
    setBtResult(null)
    setBtSig('')
    setBtRange({ start: null, end: null })
    setLiveResult(null)
    setLiveSig('')
  }, [])

  // Load a user-uploaded term-sheet JSON: normalise it through the backend
  // (legacy-field migration + inverted-ticker fix), then treat it like a config.
  const loadUploadedConfig = useCallback(async (raw: unknown) => {
    setErrorMsg('')
    try {
      const tm = await api.parseConfig(raw)
      setConfigFile('')
      setTerms(tm)
      setResult(null); setRunSig('')
      setBtResult(null); setBtSig(''); setBtRange({ start: null, end: null })
      setLiveResult(null); setLiveSig('')
    } catch (e) {
      setErrorMsg(String(e instanceof Error ? e.message : e))
    }
  }, [])

  const btSigOf = (r: BtRange) => JSON.stringify({ t: terms, r })
  const fetchBacktest = useCallback(async (range: BtRange = btRange) => {
    if (!terms) return
    setBtStatus('running')
    setBtError('')
    try {
      const r = await api.backtest(terms, lang, range)
      setBtResult(r)
      setBtSig(JSON.stringify({ t: terms, r: range }))
      setBtStatus('idle')
    } catch (e) {
      setBtError(String(e instanceof Error ? e.message : e))
      setBtStatus('error')
    }
  }, [terms, lang, btRange])

  const applyBtRange = useCallback((r: BtRange) => { setBtRange(r); fetchBacktest(r) }, [fetchBacktest])

  const btStale = !!btResult && !!terms && btSigOf(btRange) !== btSig

  const fetchLive = useCallback(async () => {
    if (!terms) return
    setLiveStatus('running')
    setLiveError('')
    try {
      const r = await api.live(terms, lang)
      setLiveResult(r)
      setLiveSig(JSON.stringify(terms))
      setLiveStatus('idle')
    } catch (e) {
      setLiveError(String(e instanceof Error ? e.message : e))
      setLiveStatus('error')
    }
  }, [terms, lang])

  const liveStale = !!liveResult && !!terms && JSON.stringify(terms) !== liveSig

  // Auto-load the backtest / live tabs when opened and the cached result (if any)
  // no longer matches the current terms. Term edits while already on the tab show
  // a stale affordance instead of refetching on every keystroke.
  useEffect(() => {
    if (tab === 'bt' && terms && btStatus !== 'running' && btSigOf(btRange) !== btSig) {
      fetchBacktest()
    }
    if (tab === 'live' && terms && liveStatus !== 'running' && JSON.stringify(terms) !== liveSig) {
      fetchLive()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const run = useCallback(async () => {
    if (!terms) return
    setStatus('running')
    setErrorMsg('')
    // Re-run refreshes the whole report: if the backtest / live tabs have already
    // been loaded, refresh them alongside the Monte Carlo run so all stay in sync.
    if (btResult) void fetchBacktest()
    if (liveResult) void fetchLive()
    try {
      const res = await api.simulate({
        terms, n_paths: opts.n_paths, engine: opts.engine,
        seed: opts.seed, calib_years: opts.calib_years, lang,
      })
      setResult(res)
      setRunSig(sigOf(terms, opts))
      setStatus('idle')
    } catch (e) {
      setErrorMsg(String(e instanceof Error ? e.message : e))
      setStatus('error')
    }
  }, [terms, opts, lang, btResult, fetchBacktest, liveResult, fetchLive])

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
                onUploadConfig={loadUploadedConfig}
                opts={opts}
                running={status === 'running'} stale={stale} onRun={run}
                onOpenSettings={() => setSettingsOpen(true)}
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
            <Panel title={t('note_structure')} right={
              <button className="btn btn--ghost" style={{ padding: '3px 9px', fontSize: 11.5 }}
                      onClick={() => setDiagramOpen((v) => !v)}>
                {diagramOpen ? t('hide_diagram') : t('show_diagram')}
              </button>
            }>
              {diagramOpen && <NoteTimeline terms={terms} />}
              <NoteDescription terms={terms} />
              <ObservationSchedule terms={terms} />
              <IssuerCard terms={terms} />
              <UnderlyingCards terms={terms} />
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

          {tab === 'bt' && (
            <>
              {btStale && btResult && btStatus !== 'running' && (
                <div role="status" style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px',
                  background: 'var(--amber-weak)', border: '1px solid var(--amber)',
                  borderRadius: 11, fontSize: 13, color: 'var(--text)',
                }}>
                  <Icon name="refresh" size={16} />
                  <span style={{ flex: 1 }}>{t('stale_banner')}</span>
                  <button className="btn" onClick={() => fetchBacktest()} style={{ padding: '6px 12px' }}>{t('rerun')}</button>
                </div>
              )}
              {btStatus === 'running' && (
                <Panel pad={40}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 14 }}>
                    <Icon name="spinner" size={18} /> {t('loading')}
                  </div>
                </Panel>
              )}
              {btStatus === 'error' && (
                <Panel><div style={{ color: 'var(--red)', fontSize: 13 }}><strong>{t('error')}.</strong> {btError}</div></Panel>
              )}
              {btStatus !== 'running' && btResult && terms && (
                <BacktestPanel result={btResult} terms={terms} range={btRange} onApplyRange={applyBtRange} />
              )}
            </>
          )}

          {tab === 'live' && (
            <>
              {liveStale && liveResult && liveStatus !== 'running' && (
                <div role="status" style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px',
                  background: 'var(--amber-weak)', border: '1px solid var(--amber)',
                  borderRadius: 11, fontSize: 13, color: 'var(--text)',
                }}>
                  <Icon name="refresh" size={16} />
                  <span style={{ flex: 1 }}>{t('stale_banner')}</span>
                  <button className="btn" onClick={fetchLive} style={{ padding: '6px 12px' }}>{t('rerun')}</button>
                </div>
              )}
              {liveStatus === 'running' && (
                <Panel pad={40}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 14 }}>
                    <Icon name="spinner" size={18} /> {t('loading')}
                  </div>
                </Panel>
              )}
              {liveStatus === 'error' && (
                <Panel><div style={{ color: 'var(--red)', fontSize: 13 }}><strong>{t('error')}.</strong> {liveError}</div></Panel>
              )}
              {liveStatus !== 'running' && liveResult && terms && <LivePanel result={liveResult} terms={terms} />}
            </>
          )}

          {tab === 'report' && terms && <ReportPanel terms={terms} opts={opts} />}
        </main>
      </div>

      {settingsOpen && terms && (
        <SettingsOverlay
          terms={terms} onChange={setTerms}
          opts={opts} onOptsChange={setOpts}
          cppAvailable={cppAvailable}
          onClose={() => setSettingsOpen(false)} onRun={run}
        />
      )}
    </div>
  )
}
