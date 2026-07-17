import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api/client'
import { blankNote } from './lib/blankNote'
import type { BacktestResult, BtRange, ConfigMeta, LiveResult, NoteTerms, SimResult } from './api/types'
import { useI18n } from './i18n/I18nProvider'
import Header from './components/Header'
import TickerTape from './components/TickerTape'
import ErrorState from './components/ErrorState'
import SetupRail, { type RunOpts } from './components/SetupRail'
import NoteTimeline from './components/NoteTimeline'
import { noteSummary } from './lib/terms'
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
import ComparePanel from './components/ComparePanel'
import ReportPanel from './components/ReportPanel'
import BatchReportPanel from './components/BatchReportPanel'
import SettingsOverlay from './components/SettingsOverlay'
import NavMenu, { type NavItem } from './components/NavMenu'
import BrandMark from './components/BrandMark'
import Icon from './components/Icon'
import { useTour, mainTour } from './components/Tour'

type Status = 'idle' | 'running' | 'error'

/** Today as a LOCAL calendar day (YYYY-MM-DD) — not toISOString(), which is UTC
    and would flip the day at the wrong moment for most of the world. */
const todayISO = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Signature of the exact inputs a result depends on, so we can flag a displayed
    one as stale. `day` is part of it because every flow is computed against
    "today": the Monte Carlo calibrates off prices up to today, the backtest gains
    an issue window, and Current Performance is a snapshot as of today. Without it
    a tab left open across a day boundary keeps serving yesterday's answer, and
    (worse) never refetches — the terms alone haven't changed. */
const sigOf = (terms: NoteTerms, opts: RunOpts, day: string) =>
  JSON.stringify({ terms, n: opts.n_paths, e: opts.engine, s: opts.seed, c: opts.calib_years, d: day })

export default function App() {
  const { t, lang } = useI18n()
  const { start: startTour } = useTour()
  const [configs, setConfigs] = useState<ConfigMeta[]>([])
  const [configFile, setConfigFile] = useState('')
  const [terms, setTerms] = useState<NoteTerms | null>(null)
  // Variant B for A/B comparison — lifted here so both the Compare tab and the
  // Report tab (which can embed the comparison in the PDF) share one source of truth.
  const [variantB, setVariantB] = useState<NoteTerms | null>(null)
  const [opts, setOpts] = useState<RunOpts>({ n_paths: 10000, engine: 'numpy', seed: 42, calib_years: 5 })
  const [cppAvailable, setCppAvailable] = useState(false)
  const [result, setResult] = useState<SimResult | null>(null)
  const [runSig, setRunSig] = useState('')
  const [runDay, setRunDay] = useState('')   // calendar day the shown run was calibrated on
  const [status, setStatus] = useState<Status>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [tab, setTab] = useState('mc')
  // Sub-view per view, lifted out of the panels so the rail's NavMenu can drive
  // them (and each view remembers where you were when you come back).
  const [subs, setSubs] = useState<Record<string, string>>({ mc: 'summary', bt: 'outcomes' })
  // Picking a view should TAKE you there, not just swap what's rendered further
  // down the page — the main column is its own scroll pane, so without this you
  // keep whatever scroll position you had and may not see that anything changed.
  const resultsRef = useRef<HTMLDivElement>(null)
  const selectNav = useCallback((id: string, sub?: string) => {
    setTab(id)
    if (sub) setSubs((p) => ({ ...p, [id]: sub }))
    // Two frames: one for React to commit the new view, one for layout to settle
    // before we measure it. Re-picking the current view still scrolls (the state
    // doesn't change, so an effect-based approach would silently do nothing).
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      resultsRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
    }))
  }, [])
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
  // The current calendar day, re-checked on focus / tab-visibility / every minute.
  // Every result signature carries it, so a session left open overnight (or over a
  // weekend) marks its results stale and refetches instead of silently serving a
  // snapshot from a previous day. setDay with an equal string is a no-op re-render,
  // so the interval costs nothing on the 1439 minutes that don't cross midnight.
  const [day, setDay] = useState(todayISO())
  useEffect(() => {
    const check = () => setDay(todayISO())
    window.addEventListener('focus', check)
    document.addEventListener('visibilitychange', check)
    const id = setInterval(check, 60_000)
    return () => {
      window.removeEventListener('focus', check)
      document.removeEventListener('visibilitychange', check)
      clearInterval(id)
    }
  }, [])

  // Bootstrap: engine availability + config list. Start on a blank note rather
  // than auto-loading a bundled term sheet.
  useEffect(() => {
    const checkHealth = (retry = true) =>
      api.health()
        .then((h) => {
          setCppAvailable(h.cpp_engine)
          // Prefer the C++ engine by default whenever it's available (numpy is the
          // fallback); the user can still switch back manually in the run options.
          if (h.cpp_engine) setOpts((o) => (o.engine === 'numpy' ? { ...o, engine: 'cpp' } : o))
          if (!h.cpp_engine && retry) setTimeout(() => checkHealth(false), 1500)
        })
        .catch(() => { if (retry) setTimeout(() => checkHealth(false), 1500) })
    checkHealth()
    api.configs().then(setConfigs).catch((e) => setErrorMsg(String(e)))
    setTerms(blankNote())
    // First-ever visit: launch the guided tour once (it can be reopened any time
    // from "How it works"). Delayed so the layout has settled before spotlighting.
    if (!localStorage.getItem('mercator_tour_seen')) {
      localStorage.setItem('mercator_tour_seen', '1')
      setTimeout(() => startTour(mainTour(t)), 900)
    }
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

  // Signatures stamp the day the result was fetched FOR, so a result computed
  // yesterday reads as stale today (the backtest gains issue dates as history
  // grows; Current Performance is a snapshot as of today).
  const btSigOf = (r: BtRange, d: string) => JSON.stringify({ t: terms, r, d })
  const fetchBacktest = useCallback(async (range: BtRange = btRange) => {
    if (!terms) return
    setBtStatus('running')
    setBtError('')
    const d = todayISO()
    try {
      const r = await api.backtest(terms, lang, range)
      setBtResult(r)
      setBtSig(JSON.stringify({ t: terms, r: range, d }))
      setBtStatus('idle')
    } catch (e) {
      setBtError(String(e instanceof Error ? e.message : e))
      setBtStatus('error')
    }
  }, [terms, lang, btRange])

  const applyBtRange = useCallback((r: BtRange) => { setBtRange(r); fetchBacktest(r) }, [fetchBacktest])

  const btStale = !!btResult && !!terms && btSigOf(btRange, day) !== btSig

  const liveSigOf = (d: string) => JSON.stringify({ t: terms, d })
  const fetchLive = useCallback(async () => {
    if (!terms) return
    setLiveStatus('running')
    setLiveError('')
    const d = todayISO()
    try {
      const r = await api.live(terms, lang)
      setLiveResult(r)
      setLiveSig(JSON.stringify({ t: terms, d }))
      setLiveStatus('idle')
    } catch (e) {
      setLiveError(String(e instanceof Error ? e.message : e))
      setLiveStatus('error')
    }
  }, [terms, lang])

  const liveStale = !!liveResult && !!terms && liveSigOf(day) !== liveSig

  // Auto-load the backtest / live tabs when opened and the cached result (if any)
  // no longer matches the current terms OR was fetched on an earlier day. Term
  // edits while already on the tab show a stale affordance instead of refetching
  // on every keystroke; a day rollover refetches outright, since a stale "as of
  // today" snapshot is wrong rather than merely out of date.
  useEffect(() => {
    if (tab === 'bt' && terms && btStatus !== 'running' && btSigOf(btRange, day) !== btSig) {
      fetchBacktest()
    }
    if (tab === 'live' && terms && liveStatus !== 'running' && liveSigOf(day) !== liveSig) {
      fetchLive()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, day])

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
      const d = todayISO()
      setRunSig(sigOf(terms, opts, d))
      setRunDay(d)
      setStatus('idle')
    } catch (e) {
      setErrorMsg(String(e instanceof Error ? e.message : e))
      setStatus('error')
    }
  }, [terms, opts, lang, btResult, fetchBacktest, liveResult, fetchLive])

  // Unlike the backtest/live tabs, the Monte Carlo is never refetched behind the
  // user's back — a run is theirs to trigger. A day rollover just flags it, so the
  // amber re-run banner appears the next morning as well as after a terms edit.
  // The two reasons are told apart (against the run's OWN day as the baseline) so
  // the banner can say which it is: "inputs changed" vs "calibrated on an earlier
  // day" are different problems and prompt differently.
  const staleInputs = useMemo(
    () => !!result && !!runSig && !!terms && sigOf(terms, opts, runDay) !== runSig,
    [result, runSig, terms, opts, runDay],
  )
  const staleDay = !!result && !!runDay && runDay !== day
  const stale = staleInputs || staleDay

  const runMeta = result
    ? { engine: result.summary.engine, nPaths: result.summary.n_paths, stale }
    : null

  // One navigation model drives both the rail's NavMenu (desktop) and the
  // horizontal tab rows (the phone fallback, where the rail is hidden).
  const navItems: NavItem[] = [
    { id: 'mc', label: t('tab_mc'), subs: [
      { id: 'summary', label: t('sub_summary') },
      { id: 'fans', label: t('sub_fans') },
      { id: 'sample', label: t('sub_sample') },
      { id: 'explorer', label: t('sub_explorer') },
      { id: 'correlation', label: t('sub_correlation') },
    ] },
    { id: 'bt', label: t('tab_backtest'), subs: [
      { id: 'outcomes', label: t('bt_sub_outcomes') },
      { id: 'prices', label: t('bt_sub_prices') },
      { id: 'sample', label: t('bt_sub_sample') },
      { id: 'explorer', label: t('bt_sub_explorer') },
    ] },
    { id: 'live', label: t('tab_live') },
    { id: 'compare', label: t('tab_compare') },
    { id: 'report', label: t('tab_report'), icon: 'chart' },
    { id: 'batch', label: t('tab_batch') },
  ]
  const tabs = navItems.map((n) => ({ id: n.id, label: n.label }))

  return (
    <div className="ground">
      <Header terms={terms} run={runMeta} />
      {terms && <div data-tour="ticker"><TickerTape terms={terms} /></div>}

      <div className="app-layout">
        {/* Layout lives in .app-rail (not inline) so the phone media query's
            `display:none` can still win. */}
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
          <div data-tour="tabs">
            <Panel title={t('nav_heading')}>
              <NavMenu items={navItems} tab={tab} subs={subs} onSelect={selectNav} />
            </Panel>
          </div>
        </aside>

        <main className="app-main" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
          {terms && (
            <div data-tour="structure">
              <Panel title={t('note_structure')} right={
                <button className="btn btn--ghost" style={{ padding: '3px 9px', fontSize: 11.5 }}
                        onClick={() => setDiagramOpen((v) => !v)}>
                  {diagramOpen ? t('hide_diagram') : t('show_diagram')}
                </button>
              }>
                <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: -6, marginBottom: 14 }}>
                  {noteSummary(terms, t)}
                </div>
                {diagramOpen && <NoteTimeline terms={terms} />}
                <NoteDescription terms={terms} />
                <ObservationSchedule terms={terms} />
                <IssuerCard terms={terms} />
                <UnderlyingCards terms={terms} />
              </Panel>
            </div>
          )}

          {/* Phone fallback — the rail (and its NavMenu) is hidden below 640px. */}
          <div className="nav-mobile-only"><Tabs tabs={tabs} active={tab} onChange={selectNav} /></div>

          {/* Anchor the nav scrolls to, so picking a view actually takes you to it
              rather than swapping content somewhere off-screen. scroll-margin-top
              keeps it clear of the sticky chrome on the phone layout. */}
          <div ref={resultsRef} aria-hidden style={{ scrollMarginTop: 12 }} />

          {tab === 'mc' && (
            <>
              {stale && result && status !== 'running' && (
                <div role="status" style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px',
                  background: 'var(--amber-weak)', border: '1px solid var(--amber)',
                  borderRadius: 11, fontSize: 13, color: 'var(--text)',
                }}>
                  <Icon name="refresh" size={16} />
                  <span style={{ flex: 1 }}>{staleInputs ? t('stale_banner') : t('stale_banner_day')}</span>
                  <button className="btn" onClick={run} style={{ padding: '6px 12px' }}>{t('rerun')}</button>
                </div>
              )}
              {status === 'running' && <Panel><RunProgress /></Panel>}
              {status === 'error' && <ErrorState message={errorMsg} onRetry={run} />}
              {status !== 'running' && result && terms && (
                <MonteCarloPanel result={result} terms={terms} sub={subs.mc ?? 'summary'}
                                 onSubChange={(s) => setSubs((p) => ({ ...p, mc: s }))} />
              )}
              {status === 'idle' && !result && (
                <Panel pad={48}>
                  <div style={{ textAlign: 'center', maxWidth: 440, margin: '0 auto', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                    <div style={{
                      width: 52, height: 52, borderRadius: 14, marginBottom: 16,
                      background: 'var(--accent-weak)', color: 'var(--accent-text)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}><BrandMark size={28} /></div>
                    <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, fontWeight: 600, letterSpacing: '-0.01em', marginBottom: 8 }}>{t('no_run_title')}</div>
                    <div style={{ fontSize: 13.5, color: 'var(--text-muted)', lineHeight: 1.65, marginBottom: 20 }}>{t('no_run_body')}</div>
                    <button className="btn btn--primary" onClick={run}><Icon name="play" size={14} /> {t('run')}</button>
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
              {btStatus === 'error' && <ErrorState message={btError} onRetry={() => fetchBacktest()} />}
              {btStatus !== 'running' && btStatus !== 'error' && btResult && terms && (
                <BacktestPanel result={btResult} terms={terms} range={btRange} onApplyRange={applyBtRange}
                               sub={subs.bt ?? 'outcomes'} onSubChange={(s) => setSubs((p) => ({ ...p, bt: s }))} />
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
              {liveStatus === 'error' && <ErrorState message={liveError} onRetry={fetchLive} />}
              {liveStatus !== 'running' && liveResult && terms && <LivePanel result={liveResult} terms={terms} />}
            </>
          )}

          {tab === 'compare' && terms && (
            <ComparePanel terms={terms} opts={opts} cppAvailable={cppAvailable} configs={configs}
                          variantB={variantB} onVariantBChange={setVariantB} />
          )}

          {tab === 'report' && terms && <ReportPanel terms={terms} opts={opts} variantB={variantB} />}

          {tab === 'batch' && <BatchReportPanel terms={terms} opts={opts} configs={configs} />}
        </main>
      </div>

      {/* Phone: result reads first, the rail collapses to this sticky bar (Mobile doc). */}
      {terms && (
        <div className="mobile-action-bar">
          <button className="btn" style={{ flex: 1, justifyContent: 'center' }} onClick={() => setSettingsOpen(true)}>{t('edit_terms')}</button>
          <button className="btn btn--primary" style={{ flex: 1, justifyContent: 'center' }} onClick={run}>
            <Icon name="refresh" size={14} /> {t('rerun')}
          </button>
        </div>
      )}

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
