import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Branding, NoteTerms } from '../api/types'
import {
  buildTokens, resolveSpec, resolveColor, fillBackground, shapeKind,
  chamferPath, gradientAxis, fillStops, rgbCss,
  type Tokens, type ColorRef, type Fill,
} from '../lib/reportTheme'

/* Live preview of the PDF report's signature surfaces. It renders from the SAME
   theme spec the PDF uses (reportkit/theme.py ↔ lib/reportTheme.ts), so editing
   any colour / gradient / shape / theme / cover setting updates the picture to
   match the report. Geometry is a stylised mock, not a pixel render — but the
   shape language (rounded chamfer cuts included) tracks the real document. */

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

// ── shape-aware panel ────────────────────────────────────────────────────────
// Measures itself so the chamfer SVG is drawn 1:1 in px (no distortion, real
// rounded corners). Non-chamfer shapes fall back to CSS background + radius.
let _gid = 0
function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const measure = () => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const w = Math.round(r.width), h = Math.round(r.height)
    setSize((prev) => (prev.w === w && prev.h === h ? prev : { w, h }))
  }
  // Re-measure on EVERY render (no deps): a Panel that first mounted while an
  // ancestor tab was hidden reads 0×0, and because the same Panel instance is
  // reused across theme switches its mount-effect never re-runs. Measuring each
  // render self-corrects once the tab is visible; setSize bails when unchanged,
  // so there's no render loop. useLayoutEffect keeps it flicker-free.
  useLayoutEffect(measure)
  // Observer for genuine post-mount reflows (column resize, font swap).
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return { ref, size }
}

function Panel({ shape, fill, tok, radius = 8, style, contentStyle, children }: {
  shape: unknown; fill: Fill | undefined; tok: Tokens; radius?: number
  style?: React.CSSProperties; contentStyle?: React.CSSProperties; children?: React.ReactNode
}) {
  const kind = shapeKind(shape)
  const { ref, size } = useSize<HTMLDivElement>()
  const idRef = useRef<string>('')
  if (!idRef.current) idRef.current = `bpg${_gid++}`

  if (kind !== 'chamfer') {
    const br = kind === 'square' ? 0 : radius
    return (
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: br, background: fillBackground(fill, tok), ...style }}>
        <div style={{ position: 'relative', ...contentStyle }}>{children}</div>
      </div>
    )
  }

  const stops = fillStops(fill, tok)
  const solid = stops.every((c) => c === stops[0])
  const isRadial = (fill?.type === 'radial')
  const ax = gradientAxis(fill?.angle ?? 90)
  const id = idRef.current
  const paint = solid ? stops[0] : `url(#${id})`
  return (
    <div ref={ref} style={{ position: 'relative', ...style }}>
      {size.w > 1 && size.h > 1 && (
        <svg width={size.w} height={size.h} viewBox={`0 0 ${size.w} ${size.h}`} aria-hidden
             style={{ position: 'absolute', inset: 0, display: 'block' }}>
          {!solid && (
            <defs>
              {isRadial
                ? <radialGradient id={id} cx="0.5" cy="0.5" r="0.75">
                    {stops.map((c, i) => <stop key={i} offset={`${(i / (stops.length - 1)) * 100}%`} stopColor={c} />)}
                  </radialGradient>
                : <linearGradient id={id} x1={ax.x1} y1={ax.y1} x2={ax.x2} y2={ax.y2}>
                    {stops.map((c, i) => <stop key={i} offset={`${(i / (stops.length - 1)) * 100}%`} stopColor={c} />)}
                  </linearGradient>}
            </defs>
          )}
          <path d={chamferPath(size.w, size.h)} fill={paint} />
        </svg>
      )}
      <div style={{ position: 'relative', ...contentStyle }}>{children}</div>
    </div>
  )
}

// Faint chamfered "hex" dots — the hexCluster watermark, approximated.
function HexDots({ cut = 3 }: { cut?: number }) {
  const clip = `polygon(0 0, calc(100% - ${cut}px) 0, 100% ${cut}px, 100% 100%, ${cut}px 100%, 0 calc(100% - ${cut}px))`
  return (
    <div style={{ position: 'absolute', top: 6, right: 10, display: 'flex', gap: 4, opacity: 0.14, zIndex: 1 }}>
      {[10, 7, 5].map((s, i) => (
        <div key={i} style={{ width: s, height: s, background: '#fff', clipPath: clip }} />
      ))}
    </div>
  )
}

// ── embedded-font @font-face injection ───────────────────────────────────────
const _STYLE_MAP: Record<string, [string, string]> = {
  Regular: ['normal', 'normal'], Bold: ['bold', 'normal'],
  Italic: ['normal', 'italic'], BoldItalic: ['bold', 'italic'],
}
function fontFaceCss(files: Record<string, string> | undefined, family: string): string {
  if (!files) return ''
  return Object.entries(files).map(([style, b64]) => {
    const [w, st] = _STYLE_MAP[style] ?? ['normal', 'normal']
    const src = String(b64).startsWith('data:') ? b64 : `data:font/ttf;base64,${b64}`
    return `@font-face{font-family:'${family}';font-weight:${w};font-style:${st};font-display:swap;src:url(${src}) format('truetype');}`
  }).join('\n')
}
// A short stable id from the payload so changing the fonts busts the @font-face cache.
function fontKey(files: Record<string, string> | undefined): string {
  if (!files) return ''
  const keys = Object.keys(files).sort().join(',')
  const len = Object.values(files).reduce((n, v) => n + v.length, 0)
  return `${keys}:${len}`
}

// ── cover-metric values (mirror _fcat in app/pdf_report.py) ───────────────────
const COVER_METRIC_DEFAULT = ['coupon_pa', 'maturity', 'knock_in_barrier']
function pct0(v?: number) { return `${Math.round((v ?? 0) * 100)}%` }
function metricValue(k: string, terms?: NoteTerms): string {
  if (!terms) return ''
  switch (k) {
    case 'maturity': return `${Math.round((terms.maturity ?? 0) * 12)}M`
    case 'coupon_pa': return `${((terms.coupon_pa ?? 0) * 100).toFixed(2)}%`
    case 'coupon_barrier': return pct0(terms.coupon_barrier)
    case 'autocall_barrier': return pct0(terms.autocall_barrier)
    case 'knock_in_barrier': return pct0(terms.knock_in_barrier)
    case 'protection_level': return pct0(terms.protection_level ?? 1)
    case 'participation_rate': return pct0(terms.participation_rate ?? 1)
    case 'issue_date': return terms.issue_date ?? ''
    case 'issuer': return terms.issuer ?? ''
    default: return ''
  }
}

export default function BrandPreview({ brand, noteName, terms, coverMetrics, metricLabel }: {
  brand: Branding; noteName?: string; terms?: NoteTerms
  coverMetrics?: string[]; metricLabel?: (k: string) => string
}) {
  const tok: Tokens = buildTokens(brand)
  const spec = resolveSpec(brand.report_theme)
  const col = (ref: ColorRef | undefined) => rgbCss(resolveColor(ref, tok))
  const muted = rgbCss([139, 151, 160])
  const bodyInk = rgbCss([43, 61, 79])

  const logo = dataUrl(brand.logo_base64)
  const altLogo = dataUrl(brand.cover_logo_base64)
  const sigil = dataUrl(brand.cover_sigil_base64)
  const coverPhoto = dataUrl(((brand.filler_images_base64 as string[] | undefined) ?? [])[0])
  const firm = brand.firm_name || 'Your Firm'
  const eyebrow = (brand.report_title || 'STRUCTURED NOTE').toUpperCase()
  const title = noteName || 'Sample Structured Note'
  const website = brand.website
  const contact = brand.contact
  const footerNote = brand.footer_note

  // Cover metric band — the actually-selected metrics with values from `terms`.
  const label = metricLabel ?? ((k: string) => k.replace(/_/g, ' ').toUpperCase())
  const selKeys = (coverMetrics && coverMetrics.length ? coverMetrics : COVER_METRIC_DEFAULT)
  const coverKpis = selKeys
    .map((k) => [label(k).toUpperCase(), metricValue(k, terms)] as [string, string])
    .filter(([, v]) => v !== '')
    .slice(0, 4)
  // The masthead reuses the same selection (fallback to a generic trio if empty).
  const mastKpis: [string, string][] = coverKpis.length ? coverKpis
    : [['COUPON P.A.', '12.00%'], ['MATURITY', '18M'], ['BARRIER', '55%']]

  const overlayColor = brand.cover_overlay_color || brand.primary_color || rgbToHexSafe(tok.primary)
  const overlayOpacity = brand.cover_overlay_opacity != null ? Number(brand.cover_overlay_opacity) : 0.55

  // Embedded fonts → @font-face, scoped families so the preview reflects them.
  const titleFiles = brand.title_font_files as Record<string, string> | undefined
  const bodyFiles = brand.body_font_files as Record<string, string> | undefined
  const titleFam = useMemo(() => (titleFiles ? `bp-title-${hash(fontKey(titleFiles))}` : ''), [titleFiles])
  const bodyFam = useMemo(() => (bodyFiles ? `bp-body-${hash(fontKey(bodyFiles))}` : ''), [bodyFiles])
  const faceCss = useMemo(() => `${fontFaceCss(titleFiles, titleFam)}\n${fontFaceCss(bodyFiles, bodyFam)}`, [titleFiles, bodyFiles, titleFam, bodyFam])
  const headFont = titleFam || (brand.title_font as string) || 'inherit'
  const bodyFont = bodyFam || (brand.body_font as string) || 'inherit'
  const rootFont = bodyFont !== 'inherit' ? `${bodyFont}, var(--font-sans, system-ui)` : 'var(--font-sans, system-ui)'
  const headStyle = headFont !== 'inherit' ? { fontFamily: `${headFont}, var(--font-sans, system-ui)` } : {}

  const hd = (spec.header ?? {}) as unknown as { rule?: Record<string, ColorRef | number>; tick?: Record<string, ColorRef | number> }
  const cm = (spec.cover_masthead ?? {}) as unknown as { shape?: unknown; fill?: Fill; watermark?: string; accent_rule?: Record<string, ColorRef | number> }
  const sh = (spec.secondary_head ?? {}) as unknown as {
    chip?: { size?: number; shape?: unknown; fill?: Fill; number_color?: ColorRef }
    kicker_color?: ColorRef; title_color?: ColorRef; rule_color?: ColorRef
  }
  const dv = (spec.divider ?? {}) as unknown as Record<string, unknown>
  const chip = sh.chip ?? {}

  const paletteDots: [string, RGBLike][] = [
    ['primary', tok.primary], ['accent', tok.accent], ['section rule', tok.section_rule], ['sidebar', tok.sidebar_bar],
  ]

  return (
    <div style={{
      background: '#ffffff', borderRadius: 12, border: '1px solid var(--border)',
      padding: 14, boxShadow: '0 1px 2px rgba(40,35,20,0.05)', overflow: 'hidden',
      fontFamily: rootFont,
    }}>
      {faceCss.trim() && <style dangerouslySetInnerHTML={{ __html: faceCss }} />}

      {/* ── COVER PAGE mock (full-bleed brand cover) ───────────────────── */}
      <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.09em', color: muted, marginBottom: 6 }}>COVER</div>
      <div style={{
        position: 'relative', borderRadius: 10, overflow: 'hidden', color: '#fff',
        height: 176, background: col('primary'), display: 'flex', flexDirection: 'column',
      }}>
        {coverPhoto && <img src={coverPhoto} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />}
        {coverPhoto && <div style={{ position: 'absolute', inset: 0, background: overlayColor, opacity: overlayOpacity }} />}
        {/* sidebar accent rail (sidebar_bar colour) */}
        <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 4, background: rgbCss(tok.sidebar_bar) }} />

        <div style={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '18px 16px', textAlign: 'center' }}>
          {sigil && <img src={sigil} alt="" style={{ height: 20, marginBottom: 10, objectFit: 'contain', opacity: 0.95 }} />}
          {altLogo
            ? <img src={altLogo} alt="" style={{ height: 22, maxWidth: '70%', objectFit: 'contain' }} />
            : <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: '0.01em', ...headStyle }}>{firm}</div>}
          <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.2em', marginTop: 12, color: rgbCss(tok.lime) }}>{eyebrow}</div>
          <div style={{ fontSize: 13, fontWeight: 800, marginTop: 4, lineHeight: 1.15, maxWidth: '85%', ...headStyle }}>{title}</div>
        </div>

        {/* bottom metric band (ink) */}
        <div style={{ position: 'relative', background: rgbCss(tok.ink), padding: '9px 12px', display: 'flex', alignItems: 'flex-end', gap: 12 }}>
          <div style={{ display: 'flex', gap: 14, flex: 1, flexWrap: 'wrap' }}>
            {mastKpis.map(([k, v]) => (
              <div key={k}>
                <div style={{ fontSize: 5.5, fontWeight: 700, letterSpacing: '0.1em', color: rgbCss([159, 196, 179]) }}>{k}</div>
                <div style={{ fontSize: 11, fontWeight: 800, marginTop: 1, ...headStyle }}>{v}</div>
              </div>
            ))}
          </div>
          {website && <div style={{ fontSize: 7.5, fontWeight: 700, letterSpacing: '0.05em', color: rgbCss(tok.section_rule), whiteSpace: 'nowrap', alignSelf: 'center' }}>{website}</div>}
        </div>
      </div>

      {/* ── INTERIOR PAGE ──────────────────────────────────────────────── */}
      <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.09em', color: muted, margin: '16px 0 6px' }}>INTERIOR</div>

      {/* running header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        {logo
          ? <img src={logo} alt="" style={{ height: 15, maxWidth: 120, objectFit: 'contain' }} />
          : <span style={{ fontSize: 13, fontWeight: 800, color: col('primary'), letterSpacing: '0.02em', ...headStyle }}>{firm}</span>}
        <span style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.14em', color: muted }}>{eyebrow}</span>
      </div>
      <div style={{ position: 'relative', marginTop: 6 }}>
        <div style={{ height: (Number(hd.rule?.weight) || 0.3) > 0.5 ? 2 : 1, background: col(hd.rule?.color as ColorRef) }} />
        {hd.tick && (
          <div style={{ position: 'absolute', top: -0.5, left: 0, width: Number(hd.tick.w) || 15, height: 2, background: col(hd.tick.color as ColorRef), borderRadius: 1 }} />
        )}
      </div>

      {/* cover masthead (interior summary masthead) */}
      <Panel shape={cm.shape} fill={cm.fill} tok={tok} radius={9}
        style={{ marginTop: 12, color: '#fff' }} contentStyle={{ padding: '13px 13px 12px' }}>
        {cm.watermark === 'hexCluster' && <HexDots />}
        <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.16em', color: col('lime') }}>{eyebrow}</div>
        <div style={{ fontSize: 15, fontWeight: 800, marginTop: 3, lineHeight: 1.1, ...headStyle }}>{title}</div>
        <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
          {mastKpis.map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: 6, fontWeight: 700, letterSpacing: '0.1em', color: rgbCss(resolveColor({ mix: ['lime', 'white', 0.35] }, tok)) }}>{k}</div>
              <div style={{ fontSize: 11, fontWeight: 800, marginTop: 2, ...headStyle }}>{v}</div>
            </div>
          ))}
        </div>
        {cm.accent_rule && (
          <div style={{ position: 'absolute', left: 8, right: 8, bottom: 4, height: 2, background: col(cm.accent_rule.color as ColorRef), borderRadius: 1, zIndex: 1 }} />
        )}
      </Panel>

      {/* numbered section head */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14 }}>
        <Panel shape={chip.shape} fill={chip.fill} tok={tok} radius={6}
          style={{ width: 26, height: 26, flexShrink: 0 }}
          contentStyle={{ width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800, color: col(chip.number_color), ...headStyle }}>
          01
        </Panel>
        <div>
          <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.12em', color: col(sh.kicker_color) }}>NOTE TERMS</div>
          <div style={{ fontSize: 12.5, fontWeight: 800, color: col(sh.title_color), lineHeight: 1.15, ...headStyle }}>Terms &amp; Structure</div>
        </div>
      </div>
      <div style={{ height: 1, background: col(sh.rule_color), marginTop: 6, opacity: 0.9 }} />

      {/* analytical chapter opener */}
      {(dv.style as string) === 'banner' ? (
        <Panel shape={dv.shape} fill={dv.fill as Fill} tok={tok} radius={6}
          style={{ marginTop: 12, color: '#fff' }} contentStyle={{ padding: '9px 12px' }}>
          {(dv.watermark as string) === 'hexCluster' && <HexDots cut={2} />}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: col((dv.number as { color?: ColorRef })?.color), ...headStyle }}>04</div>
            {(dv.vline as boolean) && <div style={{ width: 1, alignSelf: 'stretch', background: col((dv.vline_color as ColorRef)) }} />}
            <div>
              <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.14em', color: col(dv.kicker_color as ColorRef) }}>MONTE CARLO</div>
              <div style={{ fontSize: 12, fontWeight: 800, color: col(dv.heading_color as ColorRef), ...headStyle }}>Projected Outcomes</div>
            </div>
          </div>
        </Panel>
      ) : (
        <div style={{ marginTop: 12, position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontSize: 26, fontWeight: 800, color: col((dv.number as { color?: ColorRef })?.color), lineHeight: 1, ...headStyle }}>04</div>
            <div>
              <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.14em', color: col(dv.kicker_color as ColorRef) }}>MONTE CARLO</div>
              <div style={{ fontSize: 13, fontWeight: 800, color: col((dv.heading_color as ColorRef) ?? 'ink'), ...headStyle }}>Projected Outcomes</div>
            </div>
          </div>
          <div style={{ position: 'relative', marginTop: 7 }}>
            <div style={{ height: 1, background: col((dv.rule_color as ColorRef) ?? 'rule_soft') }} />
            <div style={{ position: 'absolute', top: -0.5, left: 0, width: 26, height: 2, background: col((dv.tick_color as ColorRef) ?? 'lime'), borderRadius: 1 }} />
          </div>
        </div>
      )}

      {/* metric tiles (panel fill) */}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        {[['EXPECTED IRR', '14.1%'], ['P(AUTOCALL)', '90%']].map(([k, v]) => (
          <div key={k} style={{ flex: 1, background: rgbCss(tok.panel), borderRadius: 7, padding: '8px 10px' }}>
            <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.08em', color: muted }}>{k}</div>
            <div style={{ fontSize: 13, fontWeight: 800, color: bodyInk, marginTop: 2, ...headStyle }}>{v}</div>
          </div>
        ))}
      </div>

      {/* footer strip — footer note / contact + palette dots */}
      {(footerNote || contact || website) && (
        <div style={{ marginTop: 14, paddingTop: 8, borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ flex: 1, fontSize: 8, color: muted, lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {footerNote || [firm, contact].filter(Boolean).join(' · ')}
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {paletteDots.map(([name, c]) => (
              <div key={name} title={name} style={{ width: 10, height: 10, borderRadius: 3, background: rgbCss(c), border: '1px solid rgba(0,0,0,0.08)' }} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// small helpers ---------------------------------------------------------------
type RGBLike = [number, number, number]
function rgbToHexSafe(t: RGBLike): string {
  return '#' + t.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')
}
function hash(s: string): string {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0
  return h.toString(36)
}
