/* Renders an underlying "card" to a PNG entirely on a <canvas> — header (logo +
   name), the four key metrics, an analyst buy/hold/sell bar, the 1Y price chart,
   and a trimmed business description. This replaces a DOM-snapshot approach
   (html-to-image), which can't rasterise the nested Plotly <svg> and hangs the
   renderer. Drawing by hand is fully deterministic and lets the export match the
   report's light palette regardless of the on-screen theme. */
import Plotly from 'plotly.js-dist-min'
import { themeFigure } from './plotlyTheme'
import type { UnderlyingMetric, UnderlyingOverride } from '../api/types'

// Report light palette.
const C = {
  bg: '#ffffff', text: '#1a2e4a', muted: '#5a6b85', faint: '#93a1b5',
  border: '#e3e9f2', tile: '#ffffff', tileEdge: 'rgba(0,0,0,0.10)',
}
const MONO_COLORS = ['#2563eb', '#0891b2', '#7c3aed', '#0d9488', '#d97706', '#db2777']
const SENT = { buy: '#16a34a', hold: '#f59e0b', sell: '#dc2626' }
const FONT = 'IBM Plex Sans, sans-serif'
const MONO = 'IBM Plex Mono, ui-monospace, monospace'

export interface CardLabels {
  marketCap: string; iv: string; vol: string; lastPrice: string; rsi: string
  analyst: string; buy: string; hold: string; sell: string
}

function loadImage(url: string): Promise<HTMLImageElement | null> {
  return new Promise((res) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => res(img)
    img.onerror = () => res(null)
    img.src = url
  })
}

/** Try logo sources in order, returning the first that loads (else null). */
async function loadFirst(urls: string[]): Promise<HTMLImageElement | null> {
  for (const u of urls) {
    if (!u) continue
    const img = await loadImage(u)
    if (img) return img
  }
  return null
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function monoColor(seed: string) {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  return MONO_COLORS[h % MONO_COLORS.length]
}

/** Greedy word-wrap into at most `maxLines` lines (last line ellipsised). */
function wrap(ctx: CanvasRenderingContext2D, text: string, maxW: number, maxLines: number): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    const t = cur ? `${cur} ${w}` : w
    if (ctx.measureText(t).width > maxW && cur) {
      lines.push(cur); cur = w
      if (lines.length === maxLines - 1) break
    } else cur = t
  }
  if (lines.length < maxLines && cur) lines.push(cur)
  // ellipsis if truncated
  const consumed = lines.join(' ').split(/\s+/).length
  if (consumed < words.length && lines.length) {
    let last = lines[lines.length - 1]
    while (ctx.measureText(`${last}…`).width > maxW && last.length) last = last.slice(0, -1)
    lines[lines.length - 1] = `${last}…`
  }
  return lines
}

export async function renderUnderlyingCard(
  m: UnderlyingMetric, override: UnderlyingOverride, logoUrls: string[], labels: CardLabels,
): Promise<string> {
  try { await (document as any).fonts?.ready } catch { /* fonts optional */ }

  const W = 600, pad = 26, dpr = 2
  const innerW = W - pad * 2
  const desc = override.description || m.business_summary || ''
  const a = override.analyst
  const aTotal = a ? a.buy + a.hold + a.sell : 0
  const hasAnalyst = !!a && aTotal > 0

  // Pre-render the chart PNG (light, white) at the target width.
  let chartImg: HTMLImageElement | null = null
  const chartW = innerW, chartH = 200
  if (m.figure) {
    try {
      const light = themeFigure(m.figure, 'light')
      const url = await Plotly.toImage(
        { data: light.data, layout: { ...light.layout, paper_bgcolor: '#fff', plot_bgcolor: '#fff', width: chartW, height: chartH, margin: { l: 46, r: 16, t: 26, b: 34 } }, config: { staticPlot: true } } as any,
        { format: 'png', width: chartW, height: chartH, scale: dpr },
      )
      chartImg = await loadImage(url)
    } catch { /* chart optional */ }
  }
  const logoImg = await loadFirst(logoUrls)

  // ── measure description ───────────────────────────────────────────────────
  const measure = document.createElement('canvas').getContext('2d')!
  measure.font = `400 13px ${FONT}`
  const descLines = desc ? wrap(measure, desc, innerW, 5) : []

  // ── compute layout heights ────────────────────────────────────────────────
  let y = pad
  const headerH = 46
  const metricsH = 50
  const analystH = hasAnalyst ? 50 : 0
  const chartBlockH = chartImg ? chartH + 16 : 0
  const descH = descLines.length ? descLines.length * 20 + 12 : 0
  const H = pad + headerH + 14 + metricsH + analystH + chartBlockH + descH + pad

  const cv = document.createElement('canvas')
  cv.width = W * dpr; cv.height = Math.round(H) * dpr
  const ctx = cv.getContext('2d')!
  ctx.scale(dpr, dpr)
  ctx.textBaseline = 'alphabetic'

  // background card
  roundRect(ctx, 0.5, 0.5, W - 1, H - 1, 16); ctx.fillStyle = C.bg; ctx.fill()
  ctx.lineWidth = 1; ctx.strokeStyle = C.border; ctx.stroke()

  // ── header: logo + name + sub ─────────────────────────────────────────────
  const tile = 40
  roundRect(ctx, pad, y, tile, tile, 11)
  ctx.save(); ctx.clip()
  ctx.fillStyle = C.tile; ctx.fillRect(pad, y, tile, tile)
  if (logoImg) {
    const s = Math.min((tile - 8) / logoImg.width, (tile - 8) / logoImg.height)
    const dw = logoImg.width * s, dh = logoImg.height * s
    ctx.drawImage(logoImg, pad + (tile - dw) / 2, y + (tile - dh) / 2, dw, dh)
  } else {
    ctx.fillStyle = monoColor(m.name || m.symbol); ctx.fillRect(pad, y, tile, tile)
    ctx.fillStyle = '#fff'; ctx.font = `600 20px ${FONT}`; ctx.textAlign = 'center'
    ctx.fillText((m.name || m.symbol).trim().charAt(0).toUpperCase(), pad + tile / 2, y + tile / 2 + 7)
    ctx.textAlign = 'left'
  }
  ctx.restore()
  if (logoImg) { roundRect(ctx, pad, y, tile, tile, 11); ctx.strokeStyle = C.tileEdge; ctx.lineWidth = 1; ctx.stroke() }

  const tx = pad + tile + 14
  ctx.fillStyle = C.text; ctx.font = `600 17px ${FONT}`; ctx.textAlign = 'left'
  ctx.fillText(m.long_name || m.name, tx, y + 17)
  ctx.fillStyle = C.muted; ctx.font = `400 12.5px ${FONT}`
  ctx.fillText([m.type, m.sector].filter(Boolean).join(' · ') || '—', tx, y + 35)
  y += headerH + 14

  // ── metrics row ───────────────────────────────────────────────────────────
  const cols = [
    [labels.marketCap, m.market_cap != null ? marketCapStr(m.market_cap) : '—'],
    [m.iv_source === 'realized' ? labels.vol : labels.iv, m.iv_3m != null ? `${(m.iv_3m * 100).toFixed(1)}%` : '—'],
    [labels.lastPrice, m.last_price != null ? `$${fmtNum(m.last_price)}` : '—'],
    [labels.rsi, m.rsi_14 != null ? Math.round(m.rsi_14).toString() : '—'],
  ]
  const colW = innerW / 4
  cols.forEach(([label, value], i) => {
    const cx = pad + i * colW
    ctx.fillStyle = C.faint; ctx.font = `600 9.5px ${FONT}`
    ctx.fillText(label.toUpperCase(), cx, y + 11)
    ctx.fillStyle = C.text; ctx.font = `600 17px ${MONO}`
    ctx.fillText(value, cx, y + 33)
  })
  y += metricsH

  // ── analyst bar ───────────────────────────────────────────────────────────
  if (hasAnalyst && a) {
    ctx.fillStyle = C.faint; ctx.font = `600 9.5px ${FONT}`
    ctx.fillText(labels.analyst.toUpperCase(), pad, y + 10)
    const barY = y + 18, barH = 8
    roundRect(ctx, pad, barY, innerW, barH, 4); ctx.save(); ctx.clip()
    let bx = pad
    ;(['buy', 'hold', 'sell'] as const).forEach((k) => {
      const w = (a[k] / aTotal) * innerW
      if (w > 0) { ctx.fillStyle = SENT[k]; ctx.fillRect(bx, barY, w, barH); bx += w }
    })
    ctx.restore()
    let lx = pad
    ;(['buy', 'hold', 'sell'] as const).forEach((k) => {
      ctx.fillStyle = SENT[k]; roundRect(ctx, lx, y + 36, 8, 8, 2); ctx.fill()
      ctx.fillStyle = C.muted; ctx.font = `400 11px ${FONT}`
      const txt = `${labels[k]} ${Math.round((a[k] / aTotal) * 100)}%`
      ctx.fillText(txt, lx + 12, y + 44)
      lx += 14 + ctx.measureText(txt).width + 16
    })
    y += analystH
  }

  // ── chart ─────────────────────────────────────────────────────────────────
  if (chartImg) {
    ctx.drawImage(chartImg, pad, y, chartW, chartH)
    y += chartBlockH
  }

  // ── description ───────────────────────────────────────────────────────────
  if (descLines.length) {
    ctx.fillStyle = C.muted; ctx.font = `400 13px ${FONT}`
    descLines.forEach((ln, i) => ctx.fillText(ln, pad, y + 12 + i * 20))
  }

  return cv.toDataURL('image/png')
}

// Local number formatters (the lib/format ones import nothing we can't reuse, but
// keeping these self-contained avoids a circular concern in the canvas path).
function marketCapStr(v: number): string {
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`
  return `$${v.toFixed(0)}`
}
function fmtNum(v: number): string {
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
