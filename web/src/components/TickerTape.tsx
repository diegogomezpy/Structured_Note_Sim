import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { fetchUnderlyingMetricsCached } from '../lib/metricsStore'
import { price as fmtPrice } from '../lib/format'
import AnimatedNumber from './AnimatedNumber'
import type { NoteTerms, Quote, UnderlyingMetric } from '../api/types'

/** Quote-screen ticker tape — Mercator · Elements. An ink bar with a viridian
    LIVE chip, then a divided row of the note's underlyings (ticker · last price ·
    signed day-change ▲/▼). Seeds from the underlying-metrics endpoint, then polls
    a lightweight quotes endpoint so it genuinely updates: the price counts to its
    new value and the cell flashes on a change. All data is real. */
const POLL_MS = 30000
const SPEED = 42   // marquee scroll speed, px/s — calm enough to read in passing

/** Compact magnitude (12.3M / 1.24B / 2.1T) for volume and market cap. */
const compact = (n: number | null | undefined): string => {
  if (n == null || !Number.isFinite(n)) return '—'
  const a = Math.abs(n)
  if (a >= 1e12) return `${(n / 1e12).toFixed(2)}T`
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return String(Math.round(n))
}

export default function TickerTape({ terms }: { terms: NoteTerms }) {
  const { lang } = useI18n()
  const tickers = terms.tickers ?? {}
  const syms = Object.keys(tickers)
  const key = syms.slice().sort().join(',') + '|' + lang

  const [rows, setRows] = useState<UnderlyingMetric[] | null>(null)
  const [quotes, setQuotes] = useState<Record<string, Quote>>({})
  const [flash, setFlash] = useState<Record<string, 'up' | 'down'>>({})
  const [hover, setHover] = useState<{ sym: string; rect: DOMRect } | null>(null)
  const prevPrice = useRef<Record<string, number>>({})
  // Continuous-scroll marquee: render the row enough times to overfill the
  // viewport (`reps` copies on each half), then translate by exactly one half so
  // the loop is seamless. Duration scales with content width so the speed stays
  // constant regardless of how many underlyings there are.
  const viewportRef = useRef<HTMLDivElement>(null)
  const seqRef = useRef<HTMLDivElement>(null)
  const [reps, setReps] = useState(1)
  const [dur, setDur] = useState(24)

  // Seed the tape from the (cached) metrics endpoint.
  useEffect(() => {
    if (!syms.length) { setRows(null); return }
    let alive = true
    fetchUnderlyingMetricsCached(tickers, lang)
      .then((r) => { if (alive) setRows(r) })
      .catch(() => { if (alive) setRows(null) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  // Poll fast quotes; flash the cells whose price moved.
  useEffect(() => {
    if (!syms.length) return
    let alive = true
    const poll = async () => {
      try {
        const q = await api.quotes(syms)
        if (!alive) return
        const f: Record<string, 'up' | 'down'> = {}
        for (const s of syms) {
          const p = q[s]?.price
          const prev = prevPrice.current[s]
          if (p != null && prev != null && p !== prev) f[s] = p > prev ? 'up' : 'down'
          if (p != null) prevPrice.current[s] = p
        }
        setQuotes(q)
        if (Object.keys(f).length) {
          setFlash(f)
          setTimeout(() => { if (alive) setFlash({}) }, 850)
        }
      } catch { /* keep the seeded values */ }
    }
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => { alive = false; clearInterval(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const nameToSym: Record<string, string> = {}
  for (const [sym, name] of Object.entries(tickers)) nameToSym[name] = sym

  // Only show underlyings that are still in the note: a removed one drops out
  // immediately (rather than lingering with stale data until the refetch lands),
  // and a newly-added one stays hidden until its seeded metrics arrive.
  const symSet = new Set(syms)
  const rowSym = (m: UnderlyingMetric) => m.symbol || nameToSym[m.name] || m.name
  const visible = (rows ?? []).filter((m) => symSet.has(rowSym(m)))
  const visibleSig = visible.map((m) => m.name).join(',')

  // Render list that retains a just-removed underlying for one beat so its cell
  // can collapse out rather than vanishing. Reconciles add/remove in place; a
  // short timer drops the leaving cells once the exit animation has played.
  const [display, setDisplay] = useState<{ m: UnderlyingMetric; leaving: boolean }[]>([])
  useEffect(() => {
    setDisplay((prev) => {
      const byName = new Map(visible.map((m) => [m.name, m]))
      const out: { m: UnderlyingMetric; leaving: boolean }[] = []
      const placed = new Set<string>()
      for (const cell of prev) {
        const m = byName.get(cell.m.name)
        if (m) { out.push({ m, leaving: false }); placed.add(m.name) }   // still present
        else if (!cell.leaving) out.push({ m: cell.m, leaving: true })   // newly removed → collapse in place
        else out.push(cell)                                              // already leaving
      }
      for (const m of visible) if (!placed.has(m.name)) out.push({ m, leaving: false })  // newly added
      return out
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleSig])
  useEffect(() => {
    if (!display.some((c) => c.leaving)) return
    const t = setTimeout(() => setDisplay((d) => d.filter((c) => !c.leaving)), 300)
    return () => clearTimeout(t)
  }, [display])

  // Fit the marquee: render enough copies to overfill the viewport and set a
  // duration that holds the scroll speed constant as the row's width changes.
  const displaySig = display.map((c) => c.m.name).join(',')
  useLayoutEffect(() => {
    const measure = () => {
      const vp = viewportRef.current, seq = seqRef.current
      if (!vp || !seq) return
      const seqW = seq.scrollWidth, vpW = vp.clientWidth
      if (seqW <= 0 || vpW <= 0) return
      const r = Math.max(1, Math.ceil(vpW / seqW))
      setReps(r)
      setDur(Math.max(14, (r * seqW) / SPEED))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [displaySig])

  if (!display.length) return null

  const UP = '#5fb89a', DOWN = '#d98b80', LIGHT = '#c8d0c9', PAPER = '#f7f5ef', RULE = '#313a33'

  const hoverM = hover ? (rows ?? []).find((mm) => rowSym(mm) === hover.sym) ?? null : null

  // One ticker cell. Repeated across marquee copies, so it's keyed by symbol
  // within each copy (the copy index keys the outer list).
  const cell = (m: UnderlyingMetric, leaving: boolean) => {
    const sym = rowSym(m)
    const price = quotes[sym]?.price ?? m.last_price
    const dc = quotes[sym]?.change ?? m.day_change
    const tone = dc == null ? LIGHT : dc >= 0 ? UP : DOWN
    const fl = flash[sym]
    const cls = [leaving ? 'tick-leaving' : '', fl === 'up' ? 'tick-up' : fl === 'down' ? 'tick-down' : ''].filter(Boolean).join(' ')
    return (
      <span key={m.name} className={cls || undefined}
        onMouseEnter={(e) => setHover({ sym, rect: e.currentTarget.getBoundingClientRect() })}
        onMouseLeave={() => setHover((h) => (h?.sym === sym ? null : h))}
        style={{
          display: 'inline-flex', alignItems: 'baseline', gap: 8, padding: '11px 18px', overflow: 'hidden',
          borderRight: `1px solid ${RULE}`, fontSize: 12, cursor: 'default',
        }}>
        <span style={{ fontWeight: 600, color: PAPER }}>{sym}</span>
        <span style={{ color: LIGHT }}>
          {price != null ? <AnimatedNumber value={price} format={fmtPrice} duration={500} /> : '—'}
        </span>
        {dc != null && (
          <span style={{ color: tone }}>{dc >= 0 ? '▲' : '▼'} {Math.abs(dc * 100).toFixed(2)}%</span>
        )}
      </span>
    )
  }

  return (
    <>
    <div className="ticker-reveal" style={{ display: 'flex', alignItems: 'stretch', background: '#1c241f', overflow: 'hidden' }}>
      <div style={{
        display: 'flex', alignItems: 'center', padding: '0 14px', background: 'var(--accent)',
        fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600, letterSpacing: '0.14em',
        textTransform: 'uppercase', color: PAPER, whiteSpace: 'nowrap', flexShrink: 0,
      }}>LIVE ·</div>
      <div ref={viewportRef} className="ticker-marquee mono">
        <div className="ticker-track" style={{ animationDuration: `${dur}s` }}>
          {Array.from({ length: 2 * reps }).map((_, copy) => (
            <div key={copy} ref={copy === 0 ? seqRef : undefined} className="ticker-seq" aria-hidden={copy > 0 || undefined}>
              {display.map(({ m, leaving }) => cell(m, leaving))}
            </div>
          ))}
        </div>
      </div>
    </div>
    {hover && <QuoteDetail sym={hover.sym} rect={hover.rect} q={quotes[hover.sym] ?? null} m={hoverM} />}
    </>
  )
}

/** A 0–100% position marker over a low→high range (day or 52-week). */
function RangeBar({ label, low, high, value }: {
  label: string; low: number | null; high: number | null; value: number | null
}) {
  if (low == null || high == null || high <= low) return null
  const frac = value == null ? null : Math.min(1, Math.max(0, (value - low) / (high - low)))
  return (
    <div style={{ marginTop: 11 }}>
      <div className="mono" style={{ fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)', marginBottom: 6 }}>{label}</div>
      <div style={{ position: 'relative', height: 5, background: 'var(--border-strong)', borderRadius: 999 }}>
        {frac != null && (
          <div style={{
            position: 'absolute', left: `${frac * 100}%`, top: '50%', width: 9, height: 9, borderRadius: '50%',
            background: 'var(--accent)', border: '2px solid var(--surface)', boxShadow: '0 0 0 1px var(--accent)',
            transform: 'translate(-50%, -50%)',
          }} />
        )}
      </div>
      <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginTop: 5 }}>
        <span>{fmtPrice(low)}</span><span>{fmtPrice(high)}</span>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
      <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{label}</span>
      <span className="mono" style={{ fontSize: 11.5, color: 'var(--text)' }}>{value}</span>
    </div>
  )
}

/** Hover quote card — anchored under the ticker cell. Combines the live quote
    (day/52-week range, open, volume) with the seeded metric (market cap, IV, RSI)
    so it's useful even before the first poll lands. Read-only (pointer-events
    none), so it never interferes with the tape's hover tracking. */
function QuoteDetail({ sym, rect, q, m }: { sym: string; rect: DOMRect; q: Quote | null; m: UnderlyingMetric | null }) {
  const { t } = useI18n()
  const W = 272
  const left = Math.min(Math.max(8, rect.left), window.innerWidth - W - 8)
  const top = rect.bottom + 8
  const price = q?.price ?? m?.last_price ?? null
  const change = q?.change ?? m?.day_change ?? null
  const mktcap = q?.market_cap ?? m?.market_cap ?? null
  const name = m?.long_name || m?.name || sym
  const tone = change == null ? 'var(--text-muted)' : change >= 0 ? 'var(--accent-text)' : 'var(--red)'
  return createPortal(
    <div className="quote-pop" style={{ position: 'fixed', left, top, width: W, zIndex: 1100, pointerEvents: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 15, fontWeight: 600, color: 'var(--text)' }}>{sym}</span>
        <span className="mono" style={{ fontSize: 14, color: 'var(--text)' }}>{price != null ? fmtPrice(price) : '—'}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8, marginTop: 2 }}>
        <span style={{ fontSize: 11, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 150 }}>{name}</span>
        {change != null && (
          <span className="mono" style={{ fontSize: 11.5, color: tone, flexShrink: 0 }}>
            {change >= 0 ? '▲' : '▼'} {(Math.abs(change) * 100).toFixed(2)}%
          </span>
        )}
      </div>
      <RangeBar label={t('tk_day_range')} low={q?.day_low ?? null} high={q?.day_high ?? null} value={price} />
      <RangeBar label={t('tk_52w')} low={q?.year_low ?? null} high={q?.year_high ?? null} value={price} />
      <div style={{ marginTop: 12, paddingTop: 11, borderTop: '1px solid var(--hairline)', display: 'flex', flexDirection: 'column', gap: 7 }}>
        <Stat label={t('tk_open')} value={q?.open != null ? fmtPrice(q.open) : '—'} />
        <Stat label={t('tk_prev_close')} value={q?.prev_close != null ? fmtPrice(q.prev_close) : '—'} />
        <Stat label={t('tk_volume')} value={compact(q?.volume)} />
        <Stat label={t('tk_mktcap')} value={compact(mktcap)} />
        {m?.iv_3m != null && <Stat label={t('tk_iv')} value={`${(m.iv_3m * 100).toFixed(1)}%`} />}
        {m?.rsi_14 != null && <Stat label={t('tk_rsi')} value={m.rsi_14.toFixed(0)} />}
      </div>
    </div>,
    document.body,
  )
}
