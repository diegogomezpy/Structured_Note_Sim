import { useEffect, useState } from 'react'
import { useLogos } from '../lib/logos'

const MONO_COLORS = ['#2563eb', '#0891b2', '#7c3aed', '#0d9488', '#d97706', '#db2777']
function monoColor(seed: string): string {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  return MONO_COLORS[h % MONO_COLORS.length]
}

/** Logo on a small white tile (so transparent/dark logos read on any
    background), falling back through `fallbacks` and finally to a colored
    monogram if every URL is missing or fails to load. The shared visual behind
    TickerLogo and IssuerLogo. */
/** Route a remote logo through the same-origin proxy (so card-image capture can
    embed it and CDN hot-link blocks don't matter). Data-URLs (custom uploads)
    and already-relative URLs pass through untouched. */
export function proxify(u: string): string {
  return /^https?:\/\//i.test(u) ? `/api/logo?u=${encodeURIComponent(u)}` : u
}

export function LogoImg({
  url, name, size = 22, fallbacks = [],
}: { url: string; name: string; size?: number; fallbacks?: string[] }) {
  // Ordered candidate list; advance the cursor each time a source 404s.
  const sources = [url, ...fallbacks].filter(Boolean).map(proxify)
  const [idx, setIdx] = useState(0)
  useEffect(() => setIdx(0), [url, fallbacks.join('|')])
  const radius = Math.round(size * 0.28)
  const current = sources[idx]

  if (!current) {
    return (
      <span aria-hidden="true" style={{
        width: size, height: size, borderRadius: radius, flexShrink: 0,
        background: monoColor(name || '?'), color: '#fff',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontSize: size * 0.5, fontWeight: 600,
      }}>{(name || '?').trim().charAt(0).toUpperCase()}</span>
    )
  }
  return (
    <span style={{
      width: size, height: size, borderRadius: radius, flexShrink: 0,
      background: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden', boxShadow: '0 0 0 1px rgba(0,0,0,0.06)',
    }}>
      <img src={current} alt={name} width={size - 4} height={size - 4}
           onError={() => setIdx((i) => i + 1)} style={{ objectFit: 'contain', display: 'block' }} />
    </span>
  )
}

/** Secondary logo sources for a plain equity/ETF symbol (no index `^`, no
    exchange suffix). Financial Modeling Prep's public stock-image CDN covers
    many tickers the primary (parqet) service misses, e.g. SOFI, HOOD, COIN. */
export function tickerFallbacks(symbol: string): string[] {
  const sym = (symbol || '').trim().toUpperCase()
  if (!sym || sym.startsWith('^') || sym.includes('.')) return []
  return [`https://financialmodelingprep.com/image-stock/${encodeURIComponent(sym)}.png`]
}

export default function TickerLogo({
  symbol, name, size = 22,
}: { symbol: string; name?: string; size?: number }) {
  const url = useLogos().ticker(symbol)
  return <LogoImg url={url} name={name || symbol} size={size} fallbacks={tickerFallbacks(symbol)} />
}

export function IssuerLogo({
  issuer, size = 22,
}: { issuer: string; size?: number }) {
  const url = useLogos().issuer(issuer)
  return <LogoImg url={url} name={issuer} size={size} />
}
