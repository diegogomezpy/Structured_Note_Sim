import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Branding, NoteTerms } from '../api/types'
import {
  buildTokens, resolveSpec, resolveColor, fillBackground, shapeKind, blend,
  chamferPath, chamferPadMm, hexClusterPaths, wmSpec, gradientAxis, fillStops, rgbCss,
  type Tokens, type ColorRef, type Fill,
} from '../lib/reportTheme'

const MM_PER_PT = 0.352778  // millimetres per point (for pt→mm→px font scaling)

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
// The theme spec's geometry is in PDF millimetres; this factor maps it into
// preview pixels so editing a Cut / Radius visibly moves the shape.
const MM_PX = 1.7
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

function Panel({ shape, fill, tok, radius = 8, cPx: cOv, qPx: qOv, rPx: rOv, style, contentStyle, children }: {
  shape: unknown; fill: Fill | undefined; tok: Tokens; radius?: number
  cPx?: number; qPx?: number; rPx?: number  // pre-scaled chamfer geometry (px) — overrides mm×MM_PX
  style?: React.CSSProperties; contentStyle?: React.CSSProperties; children?: React.ReactNode
}) {
  const kind = shapeKind(shape)
  const geo = (typeof shape === 'object' && shape ? shape : {}) as { c?: number; q?: number; r?: number; radius?: number }
  const { ref, size } = useSize<HTMLDivElement>()
  const idRef = useRef<string>('')
  if (!idRef.current) idRef.current = `bpg${_gid++}`

  if (kind !== 'chamfer') {
    // Honor the spec's rounded radius (mm → px) so editing it moves the preview.
    const br = kind === 'square' ? 0 : (geo.radius != null ? geo.radius * MM_PX : radius)
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
  // Chamfer geometry in px: explicit overrides (scale-faithful callers) win;
  // otherwise scale the spec's mm geometry by MM_PX so the Cut control moves it.
  const m = Math.min(size.w, size.h)
  const cPx = cOv != null ? Math.min(cOv, m * 0.5) : (geo.c != null ? Math.min(geo.c * MM_PX, m * 0.48) : undefined)
  const qPx = qOv != null ? qOv : (geo.q != null ? geo.q * MM_PX : undefined)
  const rPx = rOv != null ? rOv : (geo.r != null ? geo.r * MM_PX : undefined)
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
          <path d={chamferPath(size.w, size.h, cPx, qPx, rPx)} fill={paint} />
        </svg>
      )}
      <div style={{ position: 'relative', ...contentStyle }}>{children}</div>
    </div>
  )
}

// Watermark drawn into a chamfer panel: the user's loaded image (faint, clipped
// to the panel silhouette) OR — when none is supplied — a FAITHFUL hex-cluster
// (transcribed from reportkit/theme.py's _hex_cluster), not the old fake dots.
// panelW/panelH and geo are the panel's px size + chamfer so the clip matches.
function Watermark({ img, enabled, panelW, panelH, geo, wm, sScale, sx, sy, variant, clusterOpacity, color }: {
  img?: string; enabled: boolean; panelW: number; panelH: number
  geo: { c?: number; q?: number; r?: number }
  wm: unknown                              // the surface's raw `watermark` value
  sScale: number; sx: number; sy: number   // legacy cluster scale + anchor, in px
  variant: number; clusterOpacity: number; color: string
}) {
  const idRef = useRef<string>('')
  if (!idRef.current) idRef.current = `bpw${_gid++}`
  const spec = wmSpec(wm)
  if (!spec) return null
  const useImg = !!(img && enabled)
  // The drawn hex cluster only appears when the CONFIG authored it (CADIEM's).
  if (!useImg && spec.source !== 'hexCluster') return null

  const clipId = idRef.current
  const clipD = chamferPath(panelW, panelH, geo.c, geo.q, geo.r)
  // Restrained placement: a fraction of the panel HEIGHT (never stretched to
  // fill), capped at 42% width, inset from the edge so it clears the chamfer,
  // vertically centred, low opacity — it sits behind the text, not over it.
  const bh = panelH * Math.max(0.05, Math.min(1, spec.scale))
  const bw = panelW * 0.42
  const inset = spec.inset != null ? spec.inset : panelH * 0.16
  const bx = spec.anchor === 'left' ? inset
    : spec.anchor === 'center' ? (panelW - bw) / 2
    : panelW - inset - bw
  const by = (panelH - bh) / 2
  return (
    <svg width={panelW} height={panelH} aria-hidden
      style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none' }}>
      <defs><clipPath id={clipId}><path d={clipD} /></clipPath></defs>
      <g clipPath={`url(#${clipId})`}>
        {useImg
          ? <image href={img} x={bx} y={by} width={bw} height={bh}
              opacity={spec.opacity} preserveAspectRatio="xMidYMid meet" />
          : hexClusterPaths(sScale, variant).map((p, i) => (
              <path key={i} d={p.d} transform={`translate(${sx + p.bx} ${sy + p.by})`}
                fill={p.filled ? color : 'none'} fillOpacity={p.filled ? clusterOpacity : undefined}
                stroke={p.filled ? 'none' : color} strokeOpacity={p.filled ? undefined : clusterOpacity} strokeWidth={p.strokeW} />
            ))}
      </g>
    </svg>
  )
}

// A generic theme-spec bag (loose typing — the shapes vary by surface).
type Spec = Record<string, unknown>
const asObj = (v: unknown): Record<string, unknown> => (typeof v === 'object' && v ? v as Record<string, unknown> : {})
const geoOf = (shape: unknown) => asObj(shape) as { c?: number; q?: number; r?: number }

// ── scale-faithful chamfer surfaces ──────────────────────────────────────────
// These measure their own width, derive a px-per-mm `s = W/178` (the PDF's
// content column is 178mm), then lay out every child in mm×s and every font in
// pt×MM_PER_PT×s — so the preview matches the real PDF geometry, not a guess.

// Summary-page masthead: dark chamfer panel, lime eyebrow, white title, muted
// subtitle, and a KPI strip with lime tick bars. Mirrors _summary_page + the
// cover_masthead hook (panel 178×58mm, chamfer 7.5/2.0/5.0, pad 9mm, KPI strip
// at MH-24, tick 0.8×14mm, label 6.3pt / value 13.5pt).
function Masthead({ tok, spec, headStyle, eyebrow, title, subtitle, kpis, wmImg, wmOn }: {
  tok: Tokens; spec: Spec; headStyle: React.CSSProperties
  eyebrow: string; title: string; subtitle: string; kpis: [string, string][]
  wmImg?: string; wmOn: boolean
}) {
  const cm = asObj(spec.cover_masthead) as { shape?: unknown; fill?: Fill; watermark?: string; accent_rule?: Record<string, ColorRef | number> }
  const geo = geoOf(cm.shape)
  const { ref, size } = useSize<HTMLDivElement>()
  const s = size.w > 0 ? size.w / 178 : 0
  const col = (r?: ColorRef) => rgbCss(resolveColor(r, tok))
  const mint = rgbCss([159, 196, 179])
  const fpx = (pt: number) => pt * MM_PER_PT * s
  const hasKpis = kpis.length > 0
  const MH = hasKpis ? 58 : 34
  const pad = chamferPadMm(geo.c)
  const stripTop = MH - 24
  const kw = (178 - 2 * pad) / Math.max(1, kpis.length)
  const cPx = (geo.c ?? 0) * s, qPx = (geo.q ?? 0) * s, rPx = (geo.r ?? 0) * s
  return (
    <div ref={ref} style={{ marginTop: 12 }}>
      {s > 0 && (
        <Panel shape={cm.shape} fill={cm.fill} tok={tok} cPx={cPx} qPx={qPx} rPx={rPx}
          style={{ height: MH * s, color: '#fff' }} contentStyle={{ position: 'relative', height: MH * s }}>
          <Watermark img={wmImg} enabled={wmOn} panelW={178 * s} panelH={MH * s} geo={{ c: cPx, q: qPx, r: rPx }}
            wm={cm.watermark} sScale={30 * s} sx={(178 - 42) * s} sy={-6 * s}
            variant={0} clusterOpacity={0.12} color="#ffffff" />
          <div style={{ position: 'absolute', left: pad * s, top: 7 * s, right: pad * s, fontSize: fpx(8), fontWeight: 700, letterSpacing: '0.13em', color: col('lime'), whiteSpace: 'nowrap', overflow: 'hidden' }}>{eyebrow}</div>
          <div style={{ position: 'absolute', left: pad * s, top: 11.5 * s, right: pad * s, fontSize: fpx(21), fontWeight: 800, lineHeight: 1.02, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...headStyle }}>{title}</div>
          <div style={{ position: 'absolute', left: pad * s, top: 24 * s, right: pad * s, fontSize: fpx(9.5), color: mint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{subtitle}</div>
          {hasKpis && <>
            <div style={{ position: 'absolute', left: pad * s, top: stripTop * s, width: (178 - 2 * pad) * s, height: Math.max(1, 0.3 * s), background: rgbCss(blend(tok.ink, [255, 255, 255], 0.18)) }} />
            {kpis.map(([k, v], i) => {
              const cx = pad + i * kw
              return (
                <div key={k}>
                  <div style={{ position: 'absolute', left: cx * s, top: (stripTop + 4) * s, width: Math.max(1.4, 0.8 * s), height: 14 * s, background: col('lime') }} />
                  <div style={{ position: 'absolute', left: (cx + 3) * s, top: (stripTop + 4) * s, width: (kw - 4) * s, fontSize: fpx(6.3), fontWeight: 700, letterSpacing: '0.04em', color: mint, lineHeight: 1.12, textTransform: 'uppercase' }}>{k}</div>
                  <div style={{ position: 'absolute', left: (cx + 3) * s, top: (stripTop + 12) * s, fontSize: fpx(13.5), fontWeight: 800, color: '#fff', whiteSpace: 'nowrap', ...headStyle }}>{v}</div>
                </div>
              )
            })}
          </>}
          {cm.accent_rule && (
            <div style={{ position: 'absolute', left: 4 * s, right: 4 * s, bottom: 1.6 * s, height: Math.max(1, 1.2 * s), background: col(cm.accent_rule.color as ColorRef), borderRadius: 1, zIndex: 1 }} />
          )}
        </Panel>
      )}
    </div>
  )
}

// Numbered secondary head: a 12mm chamfer chip (20% cut → the leaning-hexagon /
// downward-chevron silhouette), then kicker + title, then a rule. Mirrors
// SpecTheme.secondary_head (chip 12mm, chamfer 2.4/0.9/2.4, kicker at +17mm/7pt,
// title +17mm/15pt, rule at chip+2mm).
function SectionHead({ tok, spec, headStyle, num, kicker, title }: {
  tok: Tokens; spec: Spec; headStyle: React.CSSProperties; num: string; kicker: string; title: string
}) {
  const sh = asObj(spec.secondary_head) as { chip?: { size?: number; shape?: unknown; fill?: Fill; number_color?: ColorRef }; kicker_color?: ColorRef; title_color?: ColorRef; rule_color?: ColorRef }
  const chip = sh.chip ?? {}
  const geo = geoOf(chip.shape)
  const { ref, size } = useSize<HTMLDivElement>()
  const s = size.w > 0 ? size.w / 178 : 0
  const col = (r?: ColorRef) => rgbCss(resolveColor(r, tok))
  const fpx = (pt: number) => pt * MM_PER_PT * s
  const chipMm = chip.size ?? 12
  return (
    <div ref={ref} style={{ marginTop: 14, position: 'relative', height: (chipMm + 6) * s }}>
      {s > 0 && <>
        <Panel shape={chip.shape} fill={chip.fill} tok={tok}
          cPx={(geo.c ?? 0) * s} qPx={(geo.q ?? 0) * s} rPx={(geo.r ?? 0) * s} radius={((chip.shape as { radius?: number })?.radius ?? 2.6) * s}
          style={{ position: 'absolute', left: 0, top: 0, width: chipMm * s, height: chipMm * s }}
          contentStyle={{ width: chipMm * s, height: chipMm * s, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: fpx(11), fontWeight: 800, color: col(chip.number_color), lineHeight: 1, ...headStyle }}>{num}</span>
        </Panel>
        <div style={{ position: 'absolute', left: (chipMm + 5) * s, top: 0.5 * s, fontSize: fpx(7), fontWeight: 700, letterSpacing: '0.07em', color: col(sh.kicker_color), textTransform: 'uppercase' }}>{kicker}</div>
        <div style={{ position: 'absolute', left: (chipMm + 5) * s, top: 4.8 * s, fontSize: fpx(15), fontWeight: 800, color: col(sh.title_color), lineHeight: 1.1, whiteSpace: 'nowrap', ...headStyle }}>{title}</div>
        <div style={{ position: 'absolute', left: 0, right: 0, top: (chipMm + 2) * s, height: Math.max(1, 0.4 * s), background: col(sh.rule_color), opacity: 0.9 }} />
      </>}
    </div>
  )
}

// Analytical chapter divider (banner style): chamfer banner, big number, vline,
// kicker + heading. Mirrors SpecTheme.section_divider banner branch (H 30mm,
// chamfer 4.4/1.3/3.4, number 26pt at 9mm, vline at 31mm, text at 37mm).
function DividerBanner({ tok, dv, headStyle, num, kicker, heading, wmImg, wmOn }: {
  tok: Tokens; dv: Spec; headStyle: React.CSSProperties; num: number; kicker: string; heading: string; wmImg?: string; wmOn: boolean
}) {
  const geo = geoOf(dv.shape)
  const { ref, size } = useSize<HTMLDivElement>()
  const s = size.w > 0 ? size.w / 178 : 0
  const col = (r?: ColorRef) => rgbCss(resolveColor(r, tok))
  const fpx = (pt: number) => pt * MM_PER_PT * s
  const H = (dv.height as number) ?? 30
  const cPx = (geo.c ?? 0) * s, qPx = (geo.q ?? 0) * s, rPx = (geo.r ?? 0) * s
  const numColor = (asObj(dv.number).color as ColorRef) ?? 'lime'
  return (
    <div ref={ref} style={{ marginTop: 12 }}>
      {s > 0 && (
        <Panel shape={dv.shape} fill={dv.fill as Fill} tok={tok} cPx={cPx} qPx={qPx} rPx={rPx}
          style={{ height: H * s, color: '#fff' }} contentStyle={{ position: 'relative', height: H * s }}>
          <Watermark img={wmImg} enabled={wmOn} panelW={178 * s} panelH={H * s} geo={{ c: cPx, q: qPx, r: rPx }}
            wm={dv.watermark} sScale={20 * s} sx={(178 - 30) * s} sy={-5 * s}
            variant={num % 3} clusterOpacity={0.10} color="#ffffff" />
          <div style={{ position: 'absolute', left: 9 * s, top: 9 * s, fontSize: fpx(26), fontWeight: 800, color: col(numColor), lineHeight: 1, ...headStyle }}>{num}</div>
          {(dv.vline as boolean) && <div style={{ position: 'absolute', left: 31 * s, top: 7 * s, width: Math.max(1, 0.5 * s), height: 16 * s, background: col(dv.vline_color as ColorRef) }} />}
          <div style={{ position: 'absolute', left: 37 * s, top: 7.5 * s, fontSize: fpx(7), fontWeight: 700, letterSpacing: '0.06em', color: col(dv.kicker_color as ColorRef), textTransform: 'uppercase' }}>{kicker}</div>
          <div style={{ position: 'absolute', left: 37 * s, top: 12.5 * s, fontSize: fpx(16), fontWeight: 800, color: col(dv.heading_color as ColorRef), lineHeight: 1.05, whiteSpace: 'nowrap', ...headStyle }}>{heading}</div>
        </Panel>
      )}
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
  const dv = (spec.divider ?? {}) as unknown as Record<string, unknown>
  const specBag = spec as unknown as Spec  // loose bag for the faithful sub-components
  // Cover-page background fill (solid brand colour by default; gradients allowed).
  const coverFill = ((spec.cover as { fill?: Fill } | undefined)?.fill) ?? ({ type: 'solid', color: 'primary' } as Fill)
  const disclaimer = (brand.disclaimer_body as string) || 'This document is for information purposes only and does not constitute investment advice or an offer to sell any security. Capital is at risk. Past performance is not indicative of future results.'

  // Masthead subtitle = report/series title · underlyings (mirrors the PDF).
  const tickerList = terms?.tickers ? Object.values(terms.tickers as Record<string, string>).slice(0, 5) : []
  const subtitle = [brand.report_title || 'Structured note', tickerList.join(' / ')].filter(Boolean).join('  ·  ')
  // Loadable watermark (image → used in place of the drawn hex cluster).
  const wmImg = dataUrl(brand.watermark_base64)
  const wmOn = brand.watermark_enabled !== false

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
      <PageTag n={1} label="COVER" muted={muted} first />
      <div style={{
        position: 'relative', borderRadius: 10, overflow: 'hidden', color: '#fff',
        height: 232, background: fillBackground(coverFill, tok), display: 'flex', flexDirection: 'column',
      }}>
        {coverPhoto && <img src={coverPhoto} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />}
        {coverPhoto && <div style={{ position: 'absolute', inset: 0, background: overlayColor, opacity: overlayOpacity }} />}
        {/* sidebar accent rail (sidebar_bar colour) */}
        <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 5, background: rgbCss(tok.sidebar_bar) }} />

        <div style={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '22px 18px', textAlign: 'center' }}>
          {sigil && <img src={sigil} alt="" style={{ height: 26, marginBottom: 12, objectFit: 'contain', opacity: 0.95 }} />}
          {altLogo
            ? <img src={altLogo} alt="" style={{ height: 28, maxWidth: '70%', objectFit: 'contain' }} />
            : <div style={{ fontSize: 21, fontWeight: 800, letterSpacing: '0.01em', ...headStyle }}>{firm}</div>}
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.22em', marginTop: 14, color: rgbCss(tok.lime) }}>{eyebrow}</div>
          <div style={{ fontSize: 16, fontWeight: 800, marginTop: 5, lineHeight: 1.15, maxWidth: '85%', ...headStyle }}>{title}</div>
        </div>

        {/* bottom metric band (ink) */}
        <div style={{ position: 'relative', background: rgbCss(tok.ink), padding: '11px 14px', display: 'flex', alignItems: 'flex-end', gap: 12 }}>
          <div style={{ display: 'flex', gap: 16, flex: 1, flexWrap: 'wrap' }}>
            {mastKpis.map(([k, v]) => (
              <div key={k}>
                <div style={{ fontSize: 6, fontWeight: 700, letterSpacing: '0.1em', color: rgbCss([159, 196, 179]) }}>{k}</div>
                <div style={{ fontSize: 12.5, fontWeight: 800, marginTop: 2, ...headStyle }}>{v}</div>
              </div>
            ))}
          </div>
          {website && <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.05em', color: rgbCss(tok.section_rule), whiteSpace: 'nowrap', alignSelf: 'center' }}>{website}</div>}
        </div>
      </div>

      {/* ── INTERIOR PAGE ──────────────────────────────────────────────── */}
      <PageTag n={2} label="INTERIOR · SUMMARY" muted={muted} />

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

      {/* cover masthead (interior summary masthead) — scale-faithful */}
      <Masthead tok={tok} spec={specBag} headStyle={headStyle} eyebrow={eyebrow} title={title}
        subtitle={subtitle} kpis={mastKpis} wmImg={wmImg} wmOn={wmOn} />

      {/* numbered section head — scale-faithful chamfer chip */}
      <SectionHead tok={tok} spec={specBag} headStyle={headStyle} num="01" kicker="NOTE TERMS" title="Terms & Structure" />

      {/* analytical chapter opener */}
      {(dv.style as string) === 'banner' ? (
        <DividerBanner tok={tok} dv={dv} headStyle={headStyle} num={4} kicker="MONTE CARLO" heading="Projected Outcomes" wmImg={wmImg} wmOn={wmOn} />
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
        {[['EXPECTED IRR', '14.1%'], ['P(AUTOCALL)', '90%'], ['P(LOSS)', '6.2%']].map(([k, v]) => (
          <div key={k} style={{ flex: 1, background: rgbCss(tok.panel), borderRadius: 7, padding: '8px 10px' }}>
            <div style={{ fontSize: 6.5, fontWeight: 700, letterSpacing: '0.08em', color: muted }}>{k}</div>
            <div style={{ fontSize: 13, fontWeight: 800, color: bodyInk, marginTop: 2, ...headStyle }}>{v}</div>
          </div>
        ))}
      </div>

      {/* mini distribution chart — accent + secondary colours */}
      <MiniChart tok={tok} />

      {/* ── INTERIOR PAGE 2 · terms table + callout ────────────────────── */}
      <PageTag n={3} label="INTERIOR · NOTE TERMS" muted={muted} />
      {/* numbered section head — scale-faithful chamfer chip */}
      <SectionHead tok={tok} spec={specBag} headStyle={headStyle} num="02" kicker="TERM SHEET" title="Key Economic Terms" />
      <div style={{ marginTop: 10, border: `1px solid ${rgbCss(tok.rule_soft)}`, borderRadius: 8, overflow: 'hidden' }}>
        {mastKpis.concat([['COUPON FREQUENCY', 'Quarterly'], ['MEMORY', 'Yes']]).slice(0, 5).map(([k, v], i) => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 11px', fontSize: 9.5,
            background: i % 2 ? rgbCss(tok.panel) : '#fff', color: bodyInk }}>
            <span style={{ color: muted }}>{k}</span>
            <span style={{ fontWeight: 700, ...headStyle }}>{v}</span>
          </div>
        ))}
      </div>
      {/* callout box — accent keyline */}
      <div style={{ marginTop: 12, display: 'flex', gap: 8, background: rgbCss(tok.panel), borderRadius: 8, padding: '9px 11px', borderLeft: `3px solid ${rgbCss(tok.section_rule)}` }}>
        <div style={{ fontSize: 9, lineHeight: 1.5, color: bodyInk }}>
          <span style={{ fontWeight: 800, ...headStyle }}>Worst-of barrier.</span> Capital is protected unless the worst-performing
          underlying closes below the knock-in at maturity.
        </div>
      </div>

      {/* ── DISCLAIMER back page (full-bleed brand) ────────────────────── */}
      <PageTag n={4} label="DISCLAIMER" muted={muted} />
      <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', color: '#fff', height: 150,
        background: fillBackground(coverFill, tok), padding: '14px 16px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 5, background: rgbCss(tok.sidebar_bar) }} />
        {altLogo
          ? <img src={altLogo} alt="" style={{ height: 16, alignSelf: 'flex-start', objectFit: 'contain', opacity: 0.95 }} />
          : <div style={{ fontSize: 12, fontWeight: 800, ...headStyle }}>{firm}</div>}
        <div style={{ fontSize: 7, fontWeight: 700, letterSpacing: '0.16em', color: rgbCss(tok.lime), marginTop: 10 }}>DISCLAIMER</div>
        <div style={{ fontSize: 7.5, lineHeight: 1.55, marginTop: 5, color: 'rgba(255,255,255,0.82)',
          display: '-webkit-box', WebkitLineClamp: 5, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{disclaimer}</div>
        {website && <div style={{ marginTop: 'auto', fontSize: 7.5, fontWeight: 700, color: rgbCss(tok.section_rule) }}>{website}</div>}
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

// A small "page N" divider label between preview surfaces.
function PageTag({ n, label, muted, first }: { n: number; label: string; muted: string; first?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, margin: first ? '0 0 8px' : '18px 0 8px' }}>
      <span style={{ fontSize: 7.5, fontWeight: 800, color: muted, border: `1px solid ${muted}`, borderRadius: 20, padding: '1px 6px', letterSpacing: '0.03em' }}>PAGE {n}</span>
      <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.1em', color: muted }}>{label}</span>
      <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
    </div>
  )
}

// A stylised worst-of fan — shows the accent + secondary palette colours in a
// chart context so those tokens are reflected too.
function MiniChart({ tok }: { tok: Tokens }) {
  const accent = rgbCss(tok.accent)
  const sec = rgbCss(tok.amber)
  const band = `rgba(${tok.accent[0]}, ${tok.accent[1]}, ${tok.accent[2]}, 0.16)`
  return (
    <svg viewBox="0 0 260 76" style={{ width: '100%', height: 'auto', marginTop: 12, display: 'block' }} aria-hidden>
      <rect x="0" y="0" width="260" height="76" rx="6" fill={rgbCss(tok.panel)} />
      {/* percentile band */}
      <path d="M8 46 C60 40 110 30 175 26 C210 24 240 22 252 21 L252 40 C240 42 210 46 175 49 C110 55 60 60 8 62 Z" fill={band} />
      {/* median line (accent) */}
      <path d="M8 54 C60 50 110 42 175 37 C210 34 240 31 252 30" fill="none" stroke={accent} strokeWidth="2" />
      {/* secondary line */}
      <path d="M8 60 C60 58 110 55 175 52 C210 50 240 49 252 48" fill="none" stroke={sec} strokeWidth="1.6" strokeDasharray="3 2" />
      {/* barrier */}
      <line x1="8" y1="66" x2="252" y2="66" stroke={rgbCss(tok.rule_soft)} strokeWidth="1" strokeDasharray="2 2" />
    </svg>
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
