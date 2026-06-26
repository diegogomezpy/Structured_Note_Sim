import { useEffect, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { fetchUnderlyingMetricsCached } from '../lib/metricsStore'
import { price as fmtPrice } from '../lib/format'
import type { NoteTerms, UnderlyingMetric } from '../api/types'

/** Quote-screen ticker tape — Mercator · Elements. An ink bar with a viridian
    LIVE chip, then a divided row of the note's underlyings (ticker · last price ·
    signed day-change ▲/▼). All data is real (the underlying-metrics endpoint);
    no arrow is shown when the day-change is unavailable. */
export default function TickerTape({ terms }: { terms: NoteTerms }) {
  const { lang } = useI18n()
  const tickers = terms.tickers ?? {}
  const key = Object.keys(tickers).sort().join(',') + '|' + lang
  const [rows, setRows] = useState<UnderlyingMetric[] | null>(null)

  // Re-runs only when the symbol set / language (the key) changes. No ref guard:
  // under StrictMode that would swallow the second mount's fetch and leave rows
  // null forever. The promise cache dedupes the actual network call.
  useEffect(() => {
    if (!Object.keys(tickers).length) { setRows(null); return }
    let alive = true
    fetchUnderlyingMetricsCached(tickers, lang)
      .then((r) => { if (alive) setRows(r) })
      .catch(() => { if (alive) setRows(null) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  // Invert {sym: name} so we can show the ticker symbol on each cell.
  const nameToSym: Record<string, string> = {}
  for (const [sym, name] of Object.entries(tickers)) nameToSym[name] = sym

  if (!rows || !rows.length) return null

  const UP = '#5fb89a', DOWN = '#d98b80', LIGHT = '#c8d0c9', PAPER = '#f7f5ef', RULE = '#313a33'

  return (
    <div style={{ display: 'flex', alignItems: 'stretch', background: '#1c241f', overflow: 'hidden' }}>
      <div style={{
        display: 'flex', alignItems: 'center', padding: '0 14px', background: 'var(--accent)',
        fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600, letterSpacing: '0.14em',
        textTransform: 'uppercase', color: PAPER, whiteSpace: 'nowrap', flexShrink: 0,
      }}>LIVE ·</div>
      <div className="mono" style={{ flex: 1, display: 'flex', alignItems: 'center', overflowX: 'auto', whiteSpace: 'nowrap', scrollbarWidth: 'none' }}>
        {rows.map((m, i) => {
          const sym = m.symbol || nameToSym[m.name] || m.name
          const dc = m.day_change
          const tone = dc == null ? LIGHT : dc >= 0 ? UP : DOWN
          return (
            <span key={m.name} title={m.name} style={{
              display: 'inline-flex', alignItems: 'baseline', gap: 8, padding: '11px 18px',
              borderRight: i < rows.length - 1 ? `1px solid ${RULE}` : 'none', fontSize: 12,
            }}>
              <span style={{ fontWeight: 600, color: PAPER }}>{sym}</span>
              <span style={{ color: LIGHT }}>{fmtPrice(m.last_price)}</span>
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
