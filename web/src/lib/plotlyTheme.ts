/* Client-side theming of the server-rendered Plotly figures.

   The backend returns ONE canonical figure with its legacy palette. Rather than
   re-fetch on a theme toggle, we transform the figure JSON in the browser:
   transparent backgrounds (so the card surface shows through), Mercator axis /
   text / font theming, and a recolour of the legacy series colours onto the
   Mercator palette (deep viridian primary, claret losses, ochre third series) —
   done in BOTH modes so the web charts match the re-skin without touching the
   server (the PDF report keeps the server palette / its branding colours). */
import type { Mode } from '../theme/ThemeProvider'

interface ThemeColors {
  text: string
  muted: string
  grid: string
  line: string
}

const PALETTE: Record<Mode, ThemeColors> = {
  light: { text: '#1c241f', muted: '#5c635b', grid: '#ece8dd', line: '#e6e1d5' },
  dark:  { text: '#eef1ea', muted: '#9aa49b', grid: '#232c24', line: '#2a332c' },
}

/* Legacy series colour → Mercator, per mode. Keys are lowercased.
   Light: viridian #15694e primary, #3f8a6f / #7eb4a0 secondaries, claret #9c3b30,
   ochre #9a6b1a, ink #1c241f. Dark: the lighter viridian/claret/ochre family. */
const SERIES_REMAP: Record<Mode, Record<string, string>> = {
  light: {
    // blue family → viridian
    '#2563eb': '#15694e', '#1d4ed8': '#15694e', '#3b82f6': '#15694e', '#1e3a8a': '#114e3a',
    '#60a5fa': '#3f8a6f', '#93c5fd': '#7eb4a0',
    // green → viridian (positive lives in the viridian family)
    '#16a34a': '#15694e',
    // teal → secondary viridian
    '#0891b2': '#3f8a6f', '#0d9488': '#3f8a6f',
    // purple → third series
    '#9b59b6': '#7eb4a0', '#a855f7': '#7eb4a0', '#7c3aed': '#3f8a6f',
    // red → claret
    '#dc2626': '#9c3b30', '#ef4444': '#9c3b30',
    // bright green → viridian
    '#22c55e': '#15694e',
    // amber/orange → ochre
    '#d97706': '#9a6b1a', '#f39c12': '#9a6b1a', '#e67e22': '#9a6b1a',
    // navy lines → ink
    '#1a2e4a': '#1c241f', '#2c3e50': '#1c241f',
    // greys / borders / gridlines → Mercator lines
    '#e5e7eb': '#e6e1d5', '#f1f5f9': '#ece8dd', '#6b7280': '#8c9189', '#64748b': '#8c9189',
    '#94a3b8': '#8c9189', '#cccccc': '#d4cdbd', '#dddddd': '#e6e1d5',
    // rgba fans / fills (worst-of bands, sample paths)
    'rgba(37,99,235,0.08)': 'rgba(21,105,78,0.08)',
    'rgba(37,99,235,0.04)': 'rgba(21,105,78,0.04)',
    'rgba(37,99,235,0.20)': 'rgba(21,105,78,0.20)',
    'rgba(37,99,235,0.40)': 'rgba(21,105,78,0.40)',
    'rgba(22,163,74,0.65)': 'rgba(21,105,78,0.65)',
    'rgba(220,38,38,0.80)': 'rgba(156,59,48,0.80)',
  },
  dark: {
    '#2563eb': '#3fae86', '#1d4ed8': '#3fae86', '#3b82f6': '#3fae86', '#1e3a8a': '#2f8f6c',
    '#60a5fa': '#5cc09c', '#93c5fd': '#88cbb2',
    '#16a34a': '#3fae86',
    '#0891b2': '#5cc09c', '#0d9488': '#5cc09c',
    '#9b59b6': '#88cbb2', '#a855f7': '#88cbb2', '#7c3aed': '#5cc09c',
    '#dc2626': '#d97a6e', '#ef4444': '#d97a6e',
    '#22c55e': '#3fae86',
    '#d97706': '#d2a24e', '#f39c12': '#d2a24e', '#e67e22': '#d2a24e',
    '#1a2e4a': '#eef1ea', '#2c3e50': '#eef1ea',
    '#e5e7eb': '#2a332c', '#f1f5f9': '#232c24', '#6b7280': '#9aa49b', '#64748b': '#9aa49b',
    '#94a3b8': '#9aa49b', '#cccccc': '#3a453c', '#dddddd': '#2a332c',
    // Mercator literals (e.g. PathExplorer outcome palette) → dark family
    '#15694e': '#3fae86', '#3f8a6f': '#5cc09c', '#9c3b30': '#d97a6e',
    'rgba(37,99,235,0.08)': 'rgba(63,174,134,0.10)',
    'rgba(37,99,235,0.04)': 'rgba(63,174,134,0.06)',
    'rgba(37,99,235,0.20)': 'rgba(63,174,134,0.24)',
    'rgba(37,99,235,0.40)': 'rgba(63,174,134,0.44)',
    'rgba(22,163,74,0.65)': 'rgba(63,174,134,0.65)',
    'rgba(220,38,38,0.80)': 'rgba(217,122,110,0.80)',
  },
}

function remapColor(c: unknown, table: Record<string, string>): unknown {
  if (typeof c !== 'string') return c
  return table[c.toLowerCase().replace(/\s+/g, '')] ?? table[c.toLowerCase()] ?? c
}

/** Recursively swap series colors anywhere a `color`/`fillcolor` lives.

    `color` is per-trace on a line but PER-POINT on a bar or marker, where Plotly
    takes an array — and a colorscale is an array of `[stop, color]` pairs. Both
    used to fall through untouched, so a chart that coloured its bars
    individually (the A/B edge-by-outcome bars) or ramped a heatmap kept the
    server's raw palette and rendered blue-and-orange inside a viridian app. */
function deepRecolor(node: unknown, table: Record<string, string>): void {
  if (Array.isArray(node)) {
    node.forEach((n) => deepRecolor(n, table))
    return
  }
  if (node && typeof node === 'object') {
    const obj = node as Record<string, unknown>
    for (const k of Object.keys(obj)) {
      const v = obj[k]
      if (k === 'color' || k === 'fillcolor') {
        if (typeof v === 'string') obj[k] = remapColor(v, table)
        else if (Array.isArray(v)) obj[k] = v.map((c) => remapColor(c, table))
      } else if (k === 'colorscale' && Array.isArray(v)) {
        // [[stop, color], …] — swap the colour, leave the stop alone.
        obj[k] = v.map((pair) => (Array.isArray(pair) && pair.length === 2
          ? [pair[0], remapColor(pair[1], table)] : pair))
      } else {
        deepRecolor(v, table)
      }
    }
  }
}

export function themeFigure(fig: any, mode: Mode): any {
  const f = structuredClone(fig)
  const c = PALETTE[mode]
  const layout = (f.layout = f.layout || {})

  layout.paper_bgcolor = 'rgba(0,0,0,0)'
  layout.plot_bgcolor = 'rgba(0,0,0,0)'
  layout.font = { ...(layout.font || {}), color: c.text, family: 'Hanken Grotesk, system-ui, sans-serif' }
  if (layout.title?.font) layout.title.font.color = c.text

  if (layout.legend) {
    layout.legend.font = { ...(layout.legend.font || {}), color: c.text }
    layout.legend.bgcolor = 'rgba(0,0,0,0)'
    layout.legend.bordercolor = c.line
  }

  for (const key of Object.keys(layout)) {
    if (!/^[xy]axis/.test(key)) continue
    const ax = layout[key]
    if (!ax || typeof ax !== 'object') continue
    ax.gridcolor = c.grid
    ax.zerolinecolor = c.line
    ax.linecolor = c.line
    ax.tickfont = { ...(ax.tickfont || {}), color: c.muted }
    if (ax.title) ax.title.font = { ...(ax.title.font || {}), color: c.muted }
  }

  // Recolour series onto the Mercator palette (both modes).
  const table = SERIES_REMAP[mode]
  deepRecolor(f.data, table)
  deepRecolor(layout.shapes, table)
  deepRecolor(layout.annotations, table)
  return f
}
