import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { useLogos } from '../lib/logos'
import { renderUnderlyingCard } from '../lib/cardImage'
import Figure from './Figure'
import Icon from './Icon'
import TickerLogo, { LogoImg, proxify, tickerFallbacks } from './TickerLogo'
import { SENTIMENT_COLOR } from './UnderlyingDetails'
import { marketCap, price, pct, num } from '../lib/format'
import type { NoteTerms, UnderlyingMetric, UnderlyingOverride } from '../api/types'

/** Split a formatted figure into its numeric stem and a trailing unit/suffix
    ($4.7 + T, 40.6 + %, 195.74 + ''), so the unit can render small + muted —
    the Mercator register's split-unit rule (matches the hero metrics). */
function splitUnit(v: string): [string, string] {
  const m = v.match(/^([^A-Za-z%]*[\d.,]+)\s*([%A-Za-z]*)$/)
  return m ? [m[1], m[2]] : [v, '']
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  const [stem, unit] = splitUnit(value)
  return (
    <div style={{ background: 'var(--surface)', padding: '11px 13px' }}>
      <div className="eyebrow" style={{ marginBottom: 7 }}>{label}</div>
      <div className="mono" style={{ fontSize: 19, fontWeight: 600, letterSpacing: '-0.01em', color: tone ?? 'var(--text)', display: 'flex', alignItems: 'baseline', gap: 1, lineHeight: 1 }}>
        {stem}{unit && <span className="fig-unit">{unit}</span>}
      </div>
    </div>
  )
}

function Description({ text }: { text: string }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const long = text.length > 240
  return (
    <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.55 }}>
      <span style={open || !long ? undefined : {
        display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
      }}>{text}</span>
      {long && (
        <button onClick={() => setOpen((o) => !o)}
          style={{ display: 'block', marginTop: 4, background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--accent-text)', fontSize: 11.5, fontFamily: 'inherit' }}>
          {open ? t('ul_less') : t('ul_more')}
        </button>
      )}
    </div>
  )
}

function Card({ m, override, chart = true }: { m: UnderlyingMetric; override: UnderlyingOverride; chart?: boolean }) {
  const { t } = useI18n()
  const logos = useLogos()
  // Prefer the fine-grained Yahoo industry ("Aerospace & Defense") over the
  // coarse sector ("Industrials"); fall back to sector when industry is absent.
  const sub = [m.type, m.industry || m.sector].filter(Boolean).join(' · ') || '—'
  const ivRealized = m.iv_source === 'realized'
  const desc = override.description || m.business_summary
  // Analyst consensus: a manual override wins, else the Yahoo autofill (m.analyst).
  const a = override.analyst ?? m.analyst
  const total = a ? (a.buy + a.hold + a.sell) : 0
  const [hover, setHover] = useState(false)
  const [saving, setSaving] = useState(false)

  // Download the whole card as a PNG. The image is composited on a <canvas>
  // (lib/cardImage) — header, metrics, analyst bar, the report-styled 1Y chart,
  // and a trimmed description — rather than snapshotting the live DOM (which can't
  // rasterise the nested Plotly SVG). Deterministic and always the report palette.
  const downloadCard = async () => {
    setSaving(true)
    try {
      const logoUrls = override.logo
        ? [override.logo]
        : [proxify(logos.ticker(m.symbol)), ...tickerFallbacks(m.symbol).map(proxify)]
      const url = await renderUnderlyingCard(m, { ...override, analyst: a }, logoUrls, {
        marketCap: t('ul_market_cap'), iv: t('ul_iv_3m'), vol: t('ul_vol_3m'),
        lastPrice: t('ul_last_price'), rsi: t('ul_rsi'), analyst: t('ul_analyst'),
        buy: t('sent_buy'), hold: t('sent_hold'), sell: t('sent_sell'),
      })
      const link = document.createElement('a')
      link.href = url; link.download = `${m.name.replace(/[^A-Za-z0-9]+/g, '_')}.png`
      document.body.appendChild(link); link.click(); link.remove()
    } catch (e) {
      console.warn('card export failed', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 13, position: 'relative' }}
         onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button onClick={downloadCard} disabled={saving} title={t('ul_download_card')} aria-label={t('ul_download_card')}
        style={{
          position: 'absolute', top: 10, right: 10, zIndex: 2, padding: 6, borderRadius: 8, cursor: saving ? 'default' : 'pointer',
          background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-muted)',
          opacity: hover || saving ? 0.95 : 0, transition: 'opacity .15s ease',
        }}>
        <Icon name={saving ? 'spinner' : 'download'} size={14} />
      </button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        {override.logo ? <LogoImg url={override.logo} name={m.name} size={30} /> : <TickerLogo symbol={m.symbol} name={m.name} size={30} />}
        <div style={{ minWidth: 0 }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, fontWeight: 600, letterSpacing: '-0.01em', color: 'var(--text)', lineHeight: 1.15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.long_name}</div>
          <div className="eyebrow" style={{ marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sub}</div>
        </div>
      </div>

      {/* Ruled register grid (hairlines via 1px gaps over a border-coloured
          ground) — matches the calibration cards. Auto-fit wraps to 2×2 in a
          narrow multi-underlying card and sits 1×4 when the card is wide. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(108px, 1fr))', gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
        <Metric label={t('ul_market_cap')} value={marketCap(m.market_cap)} />
        <Metric label={ivRealized ? t('ul_vol_3m') : t('ul_iv_3m')} value={m.iv_3m != null ? pct(m.iv_3m, 1) : '—'} />
        <Metric label={t('ul_last_price')} value={price(m.last_price)} />
        <Metric label={t('ul_rsi')} value={m.rsi_14 != null ? num(m.rsi_14, 0) : '—'} />
      </div>

      {a && total > 0 && (
        <div>
          <div className="eyebrow" style={{ marginBottom: 7 }}>{t('ul_analyst')}</div>
          <div style={{ display: 'flex', height: 8, borderRadius: 5, overflow: 'hidden', background: 'var(--surface-2)' }}>
            {(['buy', 'hold', 'sell'] as const).map((k) => a[k] > 0 && (
              <div key={k} title={`${t(`sent_${k}`)} ${a[k]}%`} style={{ flex: `${a[k]} 0 0`, background: SENTIMENT_COLOR[k] }} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 14, marginTop: 6, fontSize: 11 }}>
            {(['buy', 'hold', 'sell'] as const).map((k) => (
              <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--text-muted)' }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: SENTIMENT_COLOR[k] }} />
                {t(`sent_${k}`)} <span className="mono" style={{ color: 'var(--text)' }}>{Math.round((a[k] / total) * 100)}%</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {desc && <Description text={desc} />}
      {chart && m.figure && <div style={{ height: 190 }}><Figure fig={m.figure} name={`${m.name}_1y`} noDownload /></div>}
    </div>
  )
}

/** Per-underlying breakdown (Yahoo metrics + 1Y chart). Prefetches on note load
    (debounced for inline ticker edits) so the data is ready the moment the section
    is opened. Collapsed by default to keep the panel compact. */
export default function UnderlyingCards({ terms }: { terms: NoteTerms }) {
  const { t, lang } = useI18n()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<UnderlyingMetric[] | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [forceCharts, setForceCharts] = useState(false)
  const sig = JSON.stringify(terms.tickers)
  const rowsRef = useRef<UnderlyingMetric[] | null>(null)
  rowsRef.current = rows
  const langRef = useRef(lang)

  // Keep the breakdown in sync with the underlying set WITHOUT recomputing the
  // ones that didn't change: removing an underlying just drops its card, adding
  // one fetches only that ticker, and a rename is a no-op (metrics are keyed on
  // symbol). A language change refetches everything (the metrics carry translated
  // text). Debounced for inline ticker edits.
  useEffect(() => {
    let cancelled = false
    const tickers = terms.tickers ?? {}
    const syms = Object.keys(tickers)
    const langChanged = langRef.current !== lang
    langRef.current = lang
    const existing = (!langChanged && rowsRef.current) ? rowsRef.current : []
    const have = existing.filter((r) => syms.includes(r.symbol))
    const haveSyms = new Set(have.map((r) => r.symbol))
    const missing = syms.filter((s) => !haveSyms.has(s))
    const order = (list: UnderlyingMetric[]) =>
      syms.map((s) => list.find((m) => m.symbol === s)).filter(Boolean) as UnderlyingMetric[]

    // Nothing new to fetch (a removal, a rename, or a no-op): keep what we have.
    if (missing.length === 0) {
      const kept = order(have)
      setRows(kept.length ? kept : null)
      setStatus('idle')
      return
    }
    // Full-section spinner only on a cold load; when cards already exist, keep
    // them visible while the new ticker's metrics stream in.
    if (have.length === 0) setStatus('loading')
    const subset: Record<string, string> = {}
    missing.forEach((s) => { subset[s] = tickers[s] })
    const id = setTimeout(() => {
      api.underlyingMetrics(subset, lang)
        .then((r) => { if (!cancelled) { setRows(order([...have, ...r])); setStatus('idle') } })
        .catch(() => { if (!cancelled) setStatus(have.length ? 'idle' : 'error') })
    }, 450)
    return () => { cancelled = true; clearTimeout(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, lang])

  // Past three underlyings the per-card 1Y charts dominate and the section gets
  // cluttered — collapse them to compact metric cards by default, with a toggle.
  const many = (rows?.length ?? 0) > 3
  const showCharts = !many || forceCharts

  return (
    <div style={{ borderTop: '1px solid var(--border)' }}>
      <button onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit',
          padding: '13px 0 11px', color: 'var(--text)',
        }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{t('ul_breakdown')}</span>
          {status === 'loading' && !open && <Icon name="spinner" size={12} />}
        </span>
        <span style={{ transition: 'transform 0.15s ease', transform: open ? 'rotate(90deg)' : 'none', color: 'var(--text-faint)', fontSize: 13 }}>›</span>
      </button>

      {open && (
        <div style={{ paddingBottom: 6 }}>
          {status === 'loading' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, color: 'var(--text-muted)', fontSize: 13, padding: '8px 0' }}>
              <Icon name="spinner" size={16} /> {t('loading')}
            </div>
          )}
          {status === 'error' && <div style={{ color: 'var(--red)', fontSize: 12.5, padding: '8px 0' }}>{t('ul_load_fail')}</div>}
          {rows && status !== 'loading' && (
            <>
              {/* Editorial lead — viridian rule + serif title + supporting line,
                  mirroring the note description so the section reads in-voice. */}
              <div className="fade-up" style={{ display: 'flex', gap: 14, marginBottom: 16 }}>
                <div style={{ width: 2, borderRadius: 2, background: 'var(--accent)', flexShrink: 0 }} />
                <div style={{ maxWidth: 660 }}>
                  <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15.5, fontWeight: 600, letterSpacing: '-0.01em', color: 'var(--text)' }}>{t('ul_breakdown')}</div>
                  <div style={{ fontSize: 12.5, lineHeight: 1.6, color: 'var(--text-muted)', marginTop: 3 }}>{t('ul_breakdown_lead')}</div>
                </div>
              </div>
              {many && (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                  <button className="btn btn--ghost" style={{ padding: '4px 10px', fontSize: 11.5 }}
                          onClick={() => setForceCharts((v) => !v)}>
                    {showCharts ? t('ul_hide_charts') : t('ul_show_charts')}
                  </button>
                </div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${many ? 250 : 300}px, 1fr))`, gap: 14 }} className="fade-up">
                {rows.map((m) => <Card key={m.symbol} m={m} override={terms.underlyings?.[m.name] ?? {}} chart={showCharts} />)}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
