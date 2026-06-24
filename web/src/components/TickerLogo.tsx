import { useEffect, useState } from 'react'
import { useLogos } from '../lib/logos'

const MONO_COLORS = ['#2563eb', '#0891b2', '#7c3aed', '#0d9488', '#d97706', '#db2777']
function monoColor(seed: string): string {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  return MONO_COLORS[h % MONO_COLORS.length]
}

/** Logo on a small white tile (so transparent/dark logos read on any
    background), falling back to a colored monogram if the URL is missing or
    fails to load. The shared visual behind TickerLogo and IssuerLogo. */
export function LogoImg({
  url, name, size = 22,
}: { url: string; name: string; size?: number }) {
  const [err, setErr] = useState(false)
  useEffect(() => setErr(false), [url])
  const radius = Math.round(size * 0.28)

  if (!url || err) {
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
      <img src={url} alt={name} width={size - 4} height={size - 4}
           onError={() => setErr(true)} style={{ objectFit: 'contain', display: 'block' }} />
    </span>
  )
}

export default function TickerLogo({
  symbol, name, size = 22,
}: { symbol: string; name?: string; size?: number }) {
  const url = useLogos().ticker(symbol)
  return <LogoImg url={url} name={name || symbol} size={size} />
}

export function IssuerLogo({
  issuer, size = 22,
}: { issuer: string; size?: number }) {
  const url = useLogos().issuer(issuer)
  return <LogoImg url={url} name={issuer} size={size} />
}
