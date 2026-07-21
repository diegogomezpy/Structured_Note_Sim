import type { Branding } from '../api/types'

/* Live, theme-aware preview of the PDF report's signature surfaces. It mirrors
   the pdf_theme.py token derivation and the two themes' shapes (Hexagon =
   chamfered masthead + square lime chip + dark chapter banner; Mercator =
   rounded masthead + pale-accent chip + ghosted-numeral chapter opener), so
   editing any colour / logo / theme field updates the picture instantly. It is
   an approximation of the print output, not a pixel-exact render. */

type RGB = [number, number, number]
const WHITE: RGB = [255, 255, 255]
const BLACK: RGB = [0, 0, 0]

function hexToRgb(h?: string): RGB | null {
  if (!h) return null
  let s = h.trim().replace(/^#/, '')
  if (s.length === 3) s = s.split('').map((c) => c + c).join('')
  if (s.length !== 6 || /[^0-9a-f]/i.test(s)) return null
  const n = parseInt(s, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
const css = (t: RGB) => `rgb(${t[0]}, ${t[1]}, ${t[2]})`
const blend = (a: RGB, b: RGB, f: number): RGB =>
  [0, 1, 2].map((i) => Math.round(a[i] * (1 - f) + b[i] * f)) as RGB

function dataUrl(v?: string): string | undefined {
  if (!v) return undefined
  if (v.startsWith('data:') || v.startsWith('http') || v.startsWith('/')) return v
  let mime = 'image/png'
  if (v.startsWith('/9j/')) mime = 'image/jpeg'
  else if (v.startsWith('R0lGOD')) mime = 'image/gif'
  else if (v.startsWith('UklGR')) mime = 'image/webp'
  else if (v.startsWith('iVBOR')) mime = 'image/png'
  else if (v.includes('ftyp') || v.startsWith('AAAA')) mime = 'image/avif'
  return `data:${mime};base64,${v}`
}

// Chamfer (cut top-right + bottom-left corners) — the hexagon theme's masthead.
const chamfer = (c: number) =>
  `polygon(0 0, calc(100% - ${c}px) 0, 100% ${c}px, 100% 100%, ${c}px 100%, 0 calc(100% - ${c}px))`

export default function BrandPreview({ brand, noteName }: { brand: Branding; noteName?: string }) {
  const primary = hexToRgb(brand.primary_color) ?? [26, 46, 74]
  const accent = hexToRgb(brand.accent_color) ?? [37, 99, 235]
  const lime = hexToRgb(brand.section_rule_color) ?? accent          // section-rule / accent keyline
  const panel = hexToRgb(brand.panel_color) ?? blend(primary, WHITE, 0.93)
  const ink = blend(primary, BLACK, 0.46)                             // masthead / heading ink
  const accentWeak = blend(lime, WHITE, 0.86)                         // Mercator chip fill
  const muted: RGB = [139, 151, 160]
  const bodyInk: RGB = [43, 61, 79]
  const hair: RGB = [223, 227, 220]

  const isHex = ['cadiem', 'hexagon'].includes((brand.report_theme || 'mercator').toLowerCase())
  const logo = dataUrl(brand.logo_base64)
  const firm = brand.firm_name || 'Your Firm'
  const eyebrow = (brand.report_title || 'STRUCTURED NOTE').toUpperCase()
  const title = noteName || 'Sample Structured Note'
  const kpis: [string, string][] = [['COUPON P.A.', '12.00%'], ['MATURITY', '18M'], ['BARRIER', '55%']]

  return (
    <div style={{
      background: '#ffffff', borderRadius: 12, border: '1px solid var(--border)',
      padding: 14, boxShadow: '0 1px 2px rgba(40,35,20,0.05)', overflow: 'hidden',
      fontFamily: 'var(--font-sans, system-ui)',
    }}>
      {/* ── running header ─────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        {logo
          ? <img src={logo} alt="" style={{ height: 15, maxWidth: 120, objectFit: 'contain' }} />
          : <span style={{ fontSize: 13, fontWeight: 800, color: css(primary), letterSpacing: '0.02em' }}>{firm}</span>}
        <span style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.14em', color: css(muted) }}>{eyebrow}</span>
      </div>
      {isHex
        ? <div style={{ height: 2, background: css(primary), marginTop: 6, borderRadius: 1 }} />
        : (
          <div style={{ position: 'relative', marginTop: 6 }}>
            <div style={{ height: 1, background: css(hair) }} />
            <div style={{ position: 'absolute', top: -0.5, left: 0, width: 26, height: 2, background: css(lime), borderRadius: 1 }} />
          </div>
        )}

      {/* ── cover masthead (dark ink block; white text) ─────────────── */}
      <div style={{
        marginTop: 12, position: 'relative', background: css(ink), color: '#fff',
        padding: '13px 13px 12px', overflow: 'hidden',
        ...(isHex ? { clipPath: chamfer(13) } : { borderRadius: 9 }),
      }}>
        {isHex && (
          <div style={{ position: 'absolute', top: 6, right: 10, display: 'flex', gap: 4, opacity: 0.14 }}>
            {[10, 7, 5].map((s, i) => (
              <div key={i} style={{ width: s, height: s, background: '#fff', clipPath: chamfer(Math.max(1.5, s * 0.28)) }} />
            ))}
          </div>
        )}
        <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.16em', color: css(lime) }}>{eyebrow}</div>
        <div style={{ fontSize: 15, fontWeight: 800, marginTop: 3, lineHeight: 1.1 }}>{title}</div>
        <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
          {kpis.map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: 6, fontWeight: 700, letterSpacing: '0.1em', color: css(blend(lime, WHITE, 0.35)) }}>{k}</div>
              <div style={{ fontSize: 11, fontWeight: 800, marginTop: 2 }}>{v}</div>
            </div>
          ))}
        </div>
        {!isHex && (
          <div style={{ position: 'absolute', left: 8, right: 8, bottom: 4, height: 2, background: css(lime), borderRadius: 1 }} />
        )}
      </div>

      {/* ── numbered section head (chip + kicker + title + hairline) ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14 }}>
        <div style={{
          width: 26, height: 26, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11, fontWeight: 800,
          ...(isHex
            ? { background: css(lime), color: css(ink), clipPath: chamfer(5) }
            : { background: css(accentWeak), color: css(lime), borderRadius: 6 }),
        }}>01</div>
        <div>
          <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.12em', color: css(lime) }}>NOTE TERMS</div>
          <div style={{ fontSize: 12.5, fontWeight: 800, color: css(ink), lineHeight: 1.15 }}>Terms &amp; Structure</div>
        </div>
      </div>
      <div style={{ position: 'relative', marginTop: 6 }}>
        <div style={{ height: 1, background: css(hair) }} />
        {!isHex && <div style={{ position: 'absolute', top: -0.5, left: 0, width: 20, height: 2, background: css(lime), borderRadius: 1 }} />}
        {isHex && <div style={{ position: 'absolute', top: -1, left: 0, width: 22, height: 3, background: css(lime) }} />}
      </div>

      {/* ── analytical chapter opener ───────────────────────────────── */}
      {isHex ? (
        <div style={{
          marginTop: 12, position: 'relative', background: css(ink), color: '#fff',
          padding: '9px 12px', clipPath: chamfer(9), overflow: 'hidden',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: css(lime) }}>04</div>
            <div style={{ width: 1, alignSelf: 'stretch', background: 'rgba(255,255,255,0.3)' }} />
            <div>
              <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.14em', color: css(lime) }}>MONTE CARLO</div>
              <div style={{ fontSize: 12, fontWeight: 800 }}>Projected Outcomes</div>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 12, position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontSize: 26, fontWeight: 800, color: css(blend(lime, WHITE, 0.66)), lineHeight: 1 }}>04</div>
            <div>
              <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.14em', color: css(lime) }}>MONTE CARLO</div>
              <div style={{ fontSize: 13, fontWeight: 800, color: css(ink) }}>Projected Outcomes</div>
            </div>
          </div>
          <div style={{ position: 'relative', marginTop: 7 }}>
            <div style={{ height: 1, background: css(hair) }} />
            <div style={{ position: 'absolute', top: -0.5, left: 0, width: 26, height: 2, background: css(lime), borderRadius: 1 }} />
          </div>
        </div>
      )}

      {/* ── metric tiles (panel fill) ───────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        {[['EXPECTED IRR', '14.1%'], ['P(AUTOCALL)', '90%']].map(([k, v]) => (
          <div key={k} style={{ flex: 1, background: css(panel), borderRadius: 7, padding: '8px 10px' }}>
            <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.08em', color: css(muted) }}>{k}</div>
            <div style={{ fontSize: 13, fontWeight: 800, color: css(bodyInk), marginTop: 2 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
