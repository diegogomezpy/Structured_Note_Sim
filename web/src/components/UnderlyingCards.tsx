import { useEffect, useState } from 'react'
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

function Metric({ label, value, help }: { label: string; value: string; help?: string }) {
  return (
    <div title={help}>
      <div style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{value}</div>
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

function Card({ m, override }: { m: UnderlyingMetric; override: UnderlyingOverride }) {
  const { t } = useI18n()
  const logos = useLogos()
  const sub = [m.type, m.sector].filter(Boolean).join(' · ') || '—'
  const ivRealized = m.iv_source === 'realized'
  const desc = override.description || m.business_summary
  const a = override.analyst
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
      const url = await renderUnderlyingCard(m, override, logoUrls, {
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {override.logo ? <LogoImg url={override.logo} name={m.name} size={28} /> : <TickerLogo symbol={m.symbol} name={m.name} size={28} />}
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.long_name}</div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sub}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        <Metric label={t('ul_market_cap')} value={marketCap(m.market_cap)} />
        <Metric label={ivRealized ? t('ul_vol_3m') : t('ul_iv_3m')} value={m.iv_3m != null ? pct(m.iv_3m, 1) : '—'} />
        <Metric label={t('ul_last_price')} value={price(m.last_price)} />
        <Metric label={t('ul_rsi')} value={m.rsi_14 != null ? num(m.rsi_14, 0) : '—'} />
      </div>

      {a && total > 0 && (
        <div>
          <div style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>{t('ul_analyst')}</div>
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
      {m.figure && <div style={{ height: 190 }}><Figure fig={m.figure} name={`${m.name}_1y`} noDownload /></div>}
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
  const sig = JSON.stringify(terms.tickers)

  // Preload the moment the underlying set changes (note load / edit), debounced.
  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    const id = setTimeout(() => {
      api.underlyingMetrics(terms.tickers, lang)
        .then((r) => { if (!cancelled) { setRows(r); setStatus('idle') } })
        .catch(() => { if (!cancelled) setStatus('error') })
    }, 450)
    return () => { cancelled = true; clearTimeout(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, lang])

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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }} className="fade-up">
              {rows.map((m) => <Card key={m.symbol} m={m} override={terms.underlyings?.[m.name] ?? {}} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
