import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { fetchUnderlyingMetricsCached } from '../lib/metricsStore'
import { price as fmtPrice } from '../lib/format'
import AnimatedNumber from './AnimatedNumber'
import type { NoteTerms, UnderlyingMetric } from '../api/types'

/** Quote-screen ticker tape — Mercator · Elements. An ink bar with a viridian
    LIVE chip, then a divided row of the note's underlyings (ticker · last price ·
    signed day-change ▲/▼). Seeds from the underlying-metrics endpoint, then polls
    a lightweight quotes endpoint so it genuinely updates: the price counts to its
    new value and the cell flashes on a change. All data is real. */
const POLL_MS = 30000

export default function TickerTape({ terms }: { terms: NoteTerms }) {
  const { lang } = useI18n()
  const tickers = terms.tickers ?? {}
  const syms = Object.keys(tickers)
  const key = syms.slice().sort().join(',') + '|' + lang

  const [rows, setRows] = useState<UnderlyingMetric[] | null>(null)
  const [quotes, setQuotes] = useState<Record<string, { price: number | null; change: number | null }>>({})
  const [flash, setFlash] = useState<Record<string, 'up' | 'down'>>({})
  const prevPrice = useRef<Record<string, number>>({})

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

  if (!display.length) return null

  const UP = '#5fb89a', DOWN = '#d98b80', LIGHT = '#c8d0c9', PAPER = '#f7f5ef', RULE = '#313a33'

  return (
    <div className="ticker-reveal" style={{ display: 'flex', alignItems: 'stretch', background: '#1c241f', overflow: 'hidden' }}>
      <div style={{
        display: 'flex', alignItems: 'center', padding: '0 14px', background: 'var(--accent)',
        fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600, letterSpacing: '0.14em',
        textTransform: 'uppercase', color: PAPER, whiteSpace: 'nowrap', flexShrink: 0,
      }}>LIVE ·</div>
      <div className="mono stagger" style={{ flex: 1, display: 'flex', alignItems: 'stretch', overflowX: 'auto', whiteSpace: 'nowrap', scrollbarWidth: 'none' }}>
        {display.map(({ m, leaving }, i) => {
          const sym = rowSym(m)
          const price = quotes[sym]?.price ?? m.last_price
          const dc = quotes[sym]?.change ?? m.day_change
          const tone = dc == null ? LIGHT : dc >= 0 ? UP : DOWN
          const fl = flash[sym]
          const cls = [leaving ? 'tick-leaving' : '', fl === 'up' ? 'tick-up' : fl === 'down' ? 'tick-down' : ''].filter(Boolean).join(' ')
          return (
            <span key={m.name} title={m.name}
              className={cls || undefined}
              style={{
                display: 'inline-flex', alignItems: 'baseline', gap: 8, padding: '11px 18px', overflow: 'hidden',
                borderRight: i < display.length - 1 ? `1px solid ${RULE}` : 'none', fontSize: 12,
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
        })}
      </div>
    </div>
  )
}
