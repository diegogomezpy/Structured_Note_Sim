/* TS mirror of reportkit/theme.py — the declarative theme-spec engine.
   Keep in sync with the Python side: the built-in specs and colour/fill
   resolution here must match so the web preview renders what the PDF renders. */
import type { Branding } from '../api/types'

export type RGB = [number, number, number]
const WHITE: RGB = [255, 255, 255]
const BLACK: RGB = [0, 0, 0]
const TEXT: RGB = [43, 61, 79]

export function hexToRgb(h?: string): RGB | null {
  if (!h) return null
  let s = String(h).trim().replace(/^#/, '')
  if (s.length === 3) s = s.split('').map((c) => c + c).join('')
  if (s.length !== 6 || /[^0-9a-f]/i.test(s)) return null
  const n = parseInt(s, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
export const rgbCss = (t: RGB) => `rgb(${t[0]}, ${t[1]}, ${t[2]})`
export const rgbToHex = (t: RGB) => '#' + t.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')
export const blend = (a: RGB, b: RGB, f: number): RGB =>
  [0, 1, 2].map((i) => Math.round(a[i] * (1 - f) + b[i] * f)) as RGB

// ── palette-derived tokens (mirror build_tokens) ────────────────────────────
export interface Tokens {
  primary: RGB; accent: RGB; section_rule: RGB; panel: RGB; sidebar_bar: RGB
  ink: RGB; lime: RGB; teal: RGB; amber: RGB; amber_dark: RGB
  muted: RGB; body_ink: RGB; rule_soft: RGB; footnote_grey: RGB
}

export function buildTokens(brand: Branding): Tokens {
  const primary = hexToRgb(brand.primary_color) ?? [26, 46, 74]
  const accent = hexToRgb(brand.accent_color) ?? [37, 99, 235]
  const section_rule = hexToRgb(brand.section_rule_color) ?? accent
  const panel = hexToRgb(brand.panel_color) ?? blend(primary, WHITE, 0.93)
  const sidebar_bar = hexToRgb(brand.sidebar_bar_color as string) ?? primary
  return {
    primary, accent, section_rule, panel, sidebar_bar,
    ink: blend(primary, BLACK, 0.46),
    lime: section_rule, teal: accent,
    amber: [201, 119, 45], amber_dark: [154, 123, 18],
    muted: [139, 151, 160], body_ink: [36, 59, 51],
    rule_soft: [201, 210, 204], footnote_grey: [166, 176, 184],
  }
}

const TOKEN_KEYS: Record<string, keyof Tokens> = {
  primary: 'primary', accent: 'accent', section_rule: 'section_rule',
  panel: 'panel', sidebar_bar: 'sidebar_bar', ink: 'ink', lime: 'lime',
  teal: 'teal', amber: 'amber', amber_dark: 'amber_dark', muted: 'muted',
  body_ink: 'body_ink', rule_soft: 'rule_soft', footnote_grey: 'footnote_grey',
}
const CONST_TOKEN: Record<string, RGB> = { white: WHITE, black: BLACK, text: TEXT }

export type ColorRef =
  | string
  | RGB
  | { hex?: string; token?: ColorRef; mix?: [ColorRef, ColorRef, number] }

export function resolveColor(ref: ColorRef | undefined | null, tok: Tokens): RGB {
  if (ref == null) return tok.ink
  if (Array.isArray(ref) && ref.length === 3 && ref.every((v) => typeof v === 'number')) return ref as RGB
  if (typeof ref === 'string') {
    if (ref.startsWith('#')) return hexToRgb(ref) ?? tok.ink
    if (CONST_TOKEN[ref]) return CONST_TOKEN[ref]
    const k = TOKEN_KEYS[ref]
    return k ? tok[k] : tok.ink
  }
  if (typeof ref === 'object') {
    const r = ref as { hex?: string; token?: ColorRef; mix?: [ColorRef, ColorRef, number] }
    if (r.hex) return hexToRgb(r.hex) ?? tok.ink
    if (r.mix) return blend(resolveColor(r.mix[0], tok), resolveColor(r.mix[1], tok), Number(r.mix[2]))
    if (r.token !== undefined) return resolveColor(r.token, tok)
  }
  return tok.ink
}

// ── fills → CSS background ───────────────────────────────────────────────────
export interface Fill { type?: string; color?: ColorRef; angle?: number; stops?: Array<{ color?: ColorRef } | ColorRef> }

export function fillBackground(fill: Fill | undefined, tok: Tokens): string {
  if (!fill || !fill.type || fill.type === 'solid') return rgbCss(resolveColor(fill?.color ?? 'ink', tok))
  const stops = (fill.stops ?? []).map((s) => rgbCss(resolveColor((s as { color?: ColorRef })?.color ?? (s as ColorRef), tok)))
  if (!stops.length) return rgbCss(tok.ink)
  if (stops.length === 1) stops.push(stops[0])
  if (fill.type === 'radial') return `radial-gradient(circle at 50% 50%, ${stops.join(', ')})`
  // Python angle: 90 = top→bottom, 0 = left→right (PDF y-down). CSS: +90°.
  const css = (fill.angle ?? 90) + 90
  return `linear-gradient(${css}deg, ${stops.join(', ')})`
}

// ── built-in specs (mirror HEXAGON_SPEC / MERCATOR_SPEC in theme.py) ─────────
export const HEXAGON_SPEC = {
  name: 'Hexagon',
  header: { rule: { color: 'primary', weight: 0.6, y: 16.5 } },
  section_title: { mode: 'over', rule_weight: 0.4, keyline: { color: 'lime', w: 22, h: 1.2 } },
  secondary_head: {
    chip: { size: 12, shape: { kind: 'chamfer', c: 2.4, q: 0.9, r: 2.4 }, fill: { type: 'solid', color: 'lime' }, number_color: 'ink' },
    kicker_color: 'primary', title_color: 'ink', rule_color: 'rule_soft', rule_weight: 0.4,
  },
  divider: {
    style: 'banner', height: 30, shape: { kind: 'chamfer', c: 4.4, q: 1.3, r: 3.4 },
    fill: { type: 'solid', color: 'ink' }, watermark: 'hexCluster',
    number: { size: 26, color: 'lime', x: 9 }, vline: true, vline_color: { mix: ['ink', 'white', 0.3] },
    kicker_color: 'lime', heading_color: 'white', heading_size: 16,
  },
  void: { decoration: 'hexCluster' },
  cover_masthead: { shape: { kind: 'chamfer', c: 7.5, q: 2.0, r: 5.0 }, fill: { type: 'solid', color: 'ink' }, watermark: 'hexCluster' },
  cover_left_void: { decoration: 'hexCluster' },
  cover: { fill: { type: 'solid', color: 'primary' } },
}

export const MERCATOR_SPEC = {
  name: 'Mercator',
  header: { rule: { color: 'rule_soft', weight: 0.3, y: 16.5 }, tick: { color: 'lime', w: 15, h: 0.8, y: 16.1, radius: 0.4 } },
  section_title: { mode: 'tabAbove', rule_weight: 0.3, tab: { color: 'lime', w: 9, h: 1.0, radius: 0.5 } },
  secondary_head: {
    chip: { size: 12, shape: { kind: 'rounded', radius: 2.6 }, fill: { type: 'solid', color: { mix: ['lime', 'white', 0.86] } }, number_color: 'lime' },
    kicker_color: 'lime', title_color: 'ink', rule_color: 'rule_soft', rule_weight: 0.3,
  },
  divider: {
    style: 'editorial', height: 30, number: { size: 34, color: { mix: ['lime', 'white', 0.66] } },
    kicker_color: 'lime', heading_color: 'ink', heading_size: 17, rule_color: 'rule_soft', tick_color: 'lime',
  },
  void: { decoration: 'accentKeyline' },
  cover_masthead: { shape: { kind: 'rounded', radius: 3.0 }, fill: { type: 'solid', color: 'ink' }, accent_rule: { color: 'lime', inset: 4, h: 1.2, y_from_bottom: 1.6, radius: 0.5 } },
  cover_left_void: { decoration: 'accentKeyline' },
  cover: { fill: { type: 'solid', color: 'primary' } },
}

export type ThemeSpec = typeof MERCATOR_SPEC & Record<string, unknown>

const BUILTIN: Record<string, ThemeSpec> = {
  hexagon: HEXAGON_SPEC as unknown as ThemeSpec,
  cadiem: HEXAGON_SPEC as unknown as ThemeSpec,
  mercator: MERCATOR_SPEC as ThemeSpec,
}
export const DEFAULT_THEME = 'mercator'
export const BUILTIN_THEME_NAMES = ['mercator', 'cadiem']

function isObj(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}
function deepMerge(base: Record<string, unknown>, over: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...base }
  for (const [k, v] of Object.entries(over ?? {})) {
    out[k] = isObj(v) && isObj(out[k]) ? deepMerge(out[k] as Record<string, unknown>, v) : v
  }
  return out
}

/** Resolve `branding.report_theme` (a name string OR an inline spec, optionally
    with a "base") into a full spec — mirrors resolve_theme(). */
export function resolveSpec(reportTheme: unknown): ThemeSpec {
  if (isObj(reportTheme)) {
    const base = BUILTIN[String(reportTheme.base ?? '').toLowerCase()]
    return (base ? deepMerge(base, reportTheme) : reportTheme) as ThemeSpec
  }
  const key = String(reportTheme ?? '').toLowerCase()
  return BUILTIN[key] ?? BUILTIN[DEFAULT_THEME]
}

/** The shape kind of a spec shape ('chamfer' | 'rounded' | 'soft' | 'square'). */
export function shapeKind(shape: unknown): string {
  return typeof shape === 'string' ? shape : ((shape as { kind?: string })?.kind ?? 'rounded')
}

/** Shape → CSS, for the NON-chamfer kinds (chamfer is drawn as an SVG path via
    `chamferPath`, since CSS clip-path can't round the cut corners). rounded uses
    a px `radius`; square is plain. */
export function shapeStyle(shape: unknown, _cut: number, radius: number): Record<string, string | number> {
  const kind = shapeKind(shape)
  if (kind === 'rounded' || kind === 'soft') return { borderRadius: radius }
  return {}
}

/** Proportional chamfer dimensions in the shape's own units — mirrors
    `_chamfer_dims` in reportkit/theme.py (the 6mm cap on `r` is dropped for the
    unit-agnostic px preview). c = chamfer depth, q = chamfer-corner round,
    r = normal-corner radius. Any may be pinned by the spec. */
export function chamferDims(w: number, h: number, c?: number, q?: number, r?: number) {
  const m = Math.min(w, h)
  const C = c ?? m * 0.14
  const Q = q ?? C * 0.28
  const R = r ?? m * 0.10
  return { c: C, q: Q, r: R }
}

/** An SVG path `d` for the CADIEM chamfer — a rectangle with the top-right and
    bottom-left corners cut at 45° and ALL corners rounded. Transcribes
    `_chamfer_outline`, so the preview's chamfer matches the PDF's rounded cut
    (not a hard bevel). (0,0) = top-left; w,h in px. */
export function chamferPath(w: number, h: number, c?: number, q?: number, r?: number): string {
  const { c: C, q: Q, r: R } = chamferDims(w, h, c, q, r)
  const s = Q * 0.70710678
  const P = (a: number, b: number) => `${a.toFixed(2)} ${b.toFixed(2)}`
  return [
    `M ${P(R, 0)}`,
    `L ${P(w - C - Q, 0)}`,
    `Q ${P(w - C, 0)} ${P(w - C + s, s)}`,
    `L ${P(w - s, C - s)}`,
    `Q ${P(w, C)} ${P(w, C + Q)}`,
    `L ${P(w, h - R)}`,
    `Q ${P(w, h)} ${P(w - R, h)}`,
    `L ${P(C + Q, h)}`,
    `Q ${P(C, h)} ${P(C - s, h - s)}`,
    `L ${P(s, h - C + s)}`,
    `Q ${P(0, h - C)} ${P(0, h - C - Q)}`,
    `L ${P(0, R)}`,
    `Q ${P(0, 0)} ${P(R, 0)}`,
    'Z',
  ].join(' ')
}

/** Millimetres of interior inset that clears both chamfer cuts, mirroring the
    PDF (which hardcodes 9mm against a pinned 7.5mm cut, i.e. c + 1.5). Unlike the
    PDF this adapts upward if the Cut is dragged past 7.5 so text never collides. */
export function chamferPadMm(cMm?: number): number {
  return Math.max(9, (cMm ?? 0) + 1.5)
}

// The hex-cluster watermark — a faithful transcription of reportkit/theme.py's
// _hex_cluster. Three chamfer-hexagons per variant; each hex OVERRIDES the
// default chamfer proportions with c=0.2s, q=0.06s, r=0.2s (theme.py:206/209).
const HEX_LAYOUTS: ReadonlyArray<ReadonlyArray<readonly [number, number, number, boolean]>> = [
  [[0, 0, 1.0, false], [0.72, 0.46, 0.62, true], [0.30, 0.92, 0.44, false]],
  [[0, 0.30, 0.82, false], [0.58, 0, 1.0, false], [0.94, 0.66, 0.5, true]],
  [[0, 0, 0.7, true], [0.46, 0.36, 1.0, false], [1.04, 0.10, 0.5, false]],
]

export interface HexShape { d: string; bx: number; by: number; filled: boolean; strokeW: number }

/** The 3 chamfer-hexagon paths (in `scale` units, translate by bx/by) for a
    cluster variant — mirrors _hex_cluster's per-hex geometry. */
export function hexClusterPaths(scale: number, variant: number): HexShape[] {
  const layout = HEX_LAYOUTS[(((variant | 0) % 3) + 3) % 3]
  return layout.map(([dx, dy, sz, filled]) => {
    const s = scale * sz
    return {
      d: chamferPath(s, s, 0.20 * s, 0.06 * s, 0.20 * s),
      bx: scale * dx, by: scale * dy,
      filled, strokeW: Math.max(0.25, 0.02 * s),
    }
  })
}

// ── watermark spec (mirrors reportkit/theme.py wm_spec) ─────────────────────
export const WM_DEFAULTS = { opacity: 0.13, scale: 0.58, anchor: 'right' as const, inset: null as number | null }
export interface WmSpec { source: string; opacity: number; scale: number; anchor: string; inset: number | null }

/** Normalize a surface's `watermark` value → spec, or null for "no watermark".
    `"hexCluster"` is a value a CONFIG authors (CADIEM's), not a generic option. */
export function wmSpec(v: unknown): WmSpec | null {
  if (v == null || v === false || v === 'none') return null
  if (v === true) return { ...WM_DEFAULTS, source: 'image' }
  if (typeof v === 'string') return { ...WM_DEFAULTS, source: v }
  if (typeof v === 'object') {
    const o = v as Partial<WmSpec>
    return {
      source: o.source ?? 'image',
      opacity: o.opacity ?? WM_DEFAULTS.opacity,
      scale: o.scale ?? WM_DEFAULTS.scale,
      anchor: o.anchor ?? WM_DEFAULTS.anchor,
      inset: o.inset ?? WM_DEFAULTS.inset,
    }
  }
  return null
}

/** Gradient axis endpoints (objectBoundingBox 0..1) for an SVG linearGradient
    from a Python fill angle (90 = top→bottom, 0 = left→right). */
export function gradientAxis(angle = 90): { x1: number; y1: number; x2: number; y2: number } {
  const a = (angle * Math.PI) / 180
  const cx = Math.cos(a), cy = Math.sin(a)
  return { x1: 0.5 - 0.5 * cx, y1: 0.5 - 0.5 * cy, x2: 0.5 + 0.5 * cx, y2: 0.5 + 0.5 * cy }
}

/** Resolve a fill's ordered colour stops (each 0..1 positioned) for SVG/gradient
    rendering. Solid fills collapse to a single repeated stop. */
export function fillStops(fill: Fill | undefined, tok: Tokens): string[] {
  if (!fill || !fill.type || fill.type === 'solid') {
    const c = rgbCss(resolveColor(fill?.color ?? 'ink', tok))
    return [c, c]
  }
  const cols = (fill.stops ?? []).map((s) => rgbCss(resolveColor((s as { color?: ColorRef })?.color ?? (s as ColorRef), tok)))
  if (!cols.length) { const c = rgbCss(resolveColor(fill.color ?? 'ink', tok)); return [c, c] }
  if (cols.length === 1) cols.push(cols[0])
  return cols
}
