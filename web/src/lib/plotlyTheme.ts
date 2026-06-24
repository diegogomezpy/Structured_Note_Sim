/* Client-side theming of the server-rendered Plotly figures.

   The backend returns ONE canonical figure with the app's light palette. Rather
   than re-fetch on a theme toggle, we transform the figure JSON in the browser:
   make the backgrounds transparent (so the card surface shows through), recolor
   text/axes/legend for the active mode, and in dark mode swap a handful of
   light-only line colors (e.g. the navy worst-of line) for lighter equivalents.
   This keeps the theme toggle instant and the backend single-source. */
import type { Mode } from '../theme/ThemeProvider'

interface ThemeColors {
  text: string
  muted: string
  grid: string
  line: string
}

const PALETTE: Record<Mode, ThemeColors> = {
  light: { text: '#1a2e4a', muted: '#5a6b85', grid: '#eef2f8', line: '#e3e9f2' },
  dark:  { text: '#e7eefb', muted: '#9fb0cc', grid: '#1b2841', line: '#2a3a55' },
}

/* Light-only colors that vanish on a dark background → lighter stand-ins.
   Keys are lowercased hex; matched against any `color`-bearing field. */
const DARK_REMAP: Record<string, string> = {
  '#1a2e4a': '#cbd8ec', // navy (worst-of line / dark series)
  '#6b7280': '#94a3b8', // warm grey secondary lines
  '#e5e7eb': '#2a3a55', // light borders
  '#f1f5f9': '#1b2841', // light gridlines
  '#aaaaaa': '#64748b',
  '#aaa':    '#64748b',
}

function remapColor(c: unknown): unknown {
  if (typeof c !== 'string') return c
  return DARK_REMAP[c.toLowerCase()] ?? c
}

/** Recursively swap dark-unfriendly colors anywhere a `color`/`fillcolor` lives. */
function deepRecolor(node: unknown): void {
  if (Array.isArray(node)) {
    node.forEach(deepRecolor)
    return
  }
  if (node && typeof node === 'object') {
    const obj = node as Record<string, unknown>
    for (const k of Object.keys(obj)) {
      if ((k === 'color' || k === 'fillcolor') && typeof obj[k] === 'string') {
        obj[k] = remapColor(obj[k])
      } else {
        deepRecolor(obj[k])
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
  layout.font = { ...(layout.font || {}), color: c.text, family: 'IBM Plex Sans, sans-serif' }
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

  if (mode === 'dark') {
    deepRecolor(f.data)
    deepRecolor(layout.shapes)
    deepRecolor(layout.annotations)
  }
  return f
}
