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

/** Shape → CSS. Chamfer cuts the top-right + bottom-left corners (px `cut`);
    rounded uses a px `radius`; square is plain. */
export function shapeStyle(shape: unknown, cut: number, radius: number): Record<string, string | number> {
  const kind = typeof shape === 'string' ? shape : ((shape as { kind?: string })?.kind ?? 'rounded')
  if (kind === 'chamfer') {
    return { clipPath: `polygon(0 0, calc(100% - ${cut}px) 0, 100% ${cut}px, 100% 100%, ${cut}px 100%, 0 calc(100% - ${cut}px))` }
  }
  if (kind === 'rounded' || kind === 'soft') return { borderRadius: radius }
  return {}
}
