import type { Branding } from '../api/types'
import {
  buildTokens, resolveSpec, resolveColor, fillBackground, shapeStyle, rgbCss,
  type Tokens, type ColorRef, type Fill,
} from '../lib/reportTheme'

/* Live preview of the PDF report's signature surfaces. It renders from the SAME
   theme spec the PDF uses (reportkit/theme.py ↔ lib/reportTheme.ts), so editing
   any colour / gradient / shape / theme updates the picture to match the report.
   Geometry is approximate (a stylised mock, not a pixel render of the cover). */

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

// Faint chamfered "hex" dots — the hexCluster watermark, approximated.
function HexDots({ cut = 3 }: { cut?: number }) {
  const clip = `polygon(0 0, calc(100% - ${cut}px) 0, 100% ${cut}px, 100% 100%, ${cut}px 100%, 0 calc(100% - ${cut}px))`
  return (
    <div style={{ position: 'absolute', top: 6, right: 10, display: 'flex', gap: 4, opacity: 0.14 }}>
      {[10, 7, 5].map((s, i) => (
        <div key={i} style={{ width: s, height: s, background: '#fff', clipPath: clip }} />
      ))}
    </div>
  )
}

export default function BrandPreview({ brand, noteName }: { brand: Branding; noteName?: string }) {
  const tok: Tokens = buildTokens(brand)
  const spec = resolveSpec(brand.report_theme)
  const col = (ref: ColorRef | undefined) => rgbCss(resolveColor(ref, tok))
  const muted = rgbCss([139, 151, 160])
  const bodyInk = rgbCss([43, 61, 79])

  const logo = dataUrl(brand.logo_base64)
  const firm = brand.firm_name || 'Your Firm'
  const eyebrow = (brand.report_title || 'STRUCTURED NOTE').toUpperCase()
  const title = noteName || 'Sample Structured Note'
  const kpis: [string, string][] = [['COUPON P.A.', '12.00%'], ['MATURITY', '18M'], ['BARRIER', '55%']]

  const hd = (spec.header ?? {}) as unknown as { rule?: Record<string, ColorRef | number>; tick?: Record<string, ColorRef | number> }
  const cm = (spec.cover_masthead ?? {}) as unknown as { shape?: unknown; fill?: Fill; watermark?: string; accent_rule?: Record<string, ColorRef | number> }
  const sh = (spec.secondary_head ?? {}) as unknown as {
    chip?: { size?: number; shape?: unknown; fill?: Fill; number_color?: ColorRef }
    kicker_color?: ColorRef; title_color?: ColorRef; rule_color?: ColorRef
  }
  const dv = (spec.divider ?? {}) as unknown as Record<string, unknown>
  const chip = sh.chip ?? {}

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
          : <span style={{ fontSize: 13, fontWeight: 800, color: col('primary'), letterSpacing: '0.02em' }}>{firm}</span>}
        <span style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.14em', color: muted }}>{eyebrow}</span>
      </div>
      <div style={{ position: 'relative', marginTop: 6 }}>
        <div style={{ height: (Number(hd.rule?.weight) || 0.3) > 0.5 ? 2 : 1, background: col(hd.rule?.color as ColorRef) }} />
        {hd.tick && (
          <div style={{ position: 'absolute', top: -0.5, left: 0, width: Number(hd.tick.w) || 15, height: 2, background: col(hd.tick.color as ColorRef), borderRadius: 1 }} />
        )}
      </div>

      {/* ── cover masthead ─────────────────────────────────────────── */}
      <div style={{
        marginTop: 12, position: 'relative', color: '#fff', padding: '13px 13px 12px',
        overflow: 'hidden', background: fillBackground(cm.fill, tok),
        ...shapeStyle(cm.shape, 13, 9),
      }}>
        {cm.watermark === 'hexCluster' && <HexDots />}
        <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.16em', color: col('lime') }}>{eyebrow}</div>
        <div style={{ fontSize: 15, fontWeight: 800, marginTop: 3, lineHeight: 1.1 }}>{title}</div>
        <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
          {kpis.map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: 6, fontWeight: 700, letterSpacing: '0.1em', color: rgbCss(resolveColor({ mix: ['lime', 'white', 0.35] }, tok)) }}>{k}</div>
              <div style={{ fontSize: 11, fontWeight: 800, marginTop: 2 }}>{v}</div>
            </div>
          ))}
        </div>
        {cm.accent_rule && (
          <div style={{ position: 'absolute', left: 8, right: 8, bottom: 4, height: 2, background: col(cm.accent_rule.color as ColorRef), borderRadius: 1 }} />
        )}
      </div>

      {/* ── numbered section head ──────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14 }}>
        <div style={{
          width: 26, height: 26, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11, fontWeight: 800, color: col(chip.number_color), background: fillBackground(chip.fill, tok),
          ...shapeStyle(chip.shape, 5, 6),
        }}>01</div>
        <div>
          <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.12em', color: col(sh.kicker_color) }}>NOTE TERMS</div>
          <div style={{ fontSize: 12.5, fontWeight: 800, color: col(sh.title_color), lineHeight: 1.15 }}>Terms &amp; Structure</div>
        </div>
      </div>
      <div style={{ height: 1, background: col(sh.rule_color), marginTop: 6, opacity: 0.9 }} />

      {/* ── analytical chapter opener ──────────────────────────────── */}
      {(dv.style as string) === 'banner' ? (
        <div style={{
          marginTop: 12, position: 'relative', color: '#fff', padding: '9px 12px', overflow: 'hidden',
          background: fillBackground(dv.fill as Fill, tok), ...shapeStyle(dv.shape, 9, 6),
        }}>
          {(dv.watermark as string) === 'hexCluster' && <HexDots cut={2} />}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: col((dv.number as { color?: ColorRef })?.color) }}>04</div>
            {(dv.vline as boolean) && <div style={{ width: 1, alignSelf: 'stretch', background: col((dv.vline_color as ColorRef)) }} />}
            <div>
              <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.14em', color: col(dv.kicker_color as ColorRef) }}>MONTE CARLO</div>
              <div style={{ fontSize: 12, fontWeight: 800, color: col(dv.heading_color as ColorRef) }}>Projected Outcomes</div>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 12, position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontSize: 26, fontWeight: 800, color: col((dv.number as { color?: ColorRef })?.color), lineHeight: 1 }}>04</div>
            <div>
              <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.14em', color: col(dv.kicker_color as ColorRef) }}>MONTE CARLO</div>
              <div style={{ fontSize: 13, fontWeight: 800, color: col((dv.heading_color as ColorRef) ?? 'ink') }}>Projected Outcomes</div>
            </div>
          </div>
          <div style={{ position: 'relative', marginTop: 7 }}>
            <div style={{ height: 1, background: col((dv.rule_color as ColorRef) ?? 'rule_soft') }} />
            <div style={{ position: 'absolute', top: -0.5, left: 0, width: 26, height: 2, background: col((dv.tick_color as ColorRef) ?? 'lime'), borderRadius: 1 }} />
          </div>
        </div>
      )}

      {/* ── metric tiles (panel fill) ──────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        {[['EXPECTED IRR', '14.1%'], ['P(AUTOCALL)', '90%']].map(([k, v]) => (
          <div key={k} style={{ flex: 1, background: rgbCss(tok.panel), borderRadius: 7, padding: '8px 10px' }}>
            <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.08em', color: muted }}>{k}</div>
            <div style={{ fontSize: 13, fontWeight: 800, color: bodyInk, marginTop: 2 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
