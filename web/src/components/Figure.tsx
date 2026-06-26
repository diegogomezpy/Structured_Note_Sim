import { useMemo, useRef, useState } from 'react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'
import { useTheme } from '../theme/ThemeProvider'
import { themeFigure } from '../lib/plotlyTheme'
import Icon from './Icon'

const Plot = createPlotlyComponent(Plotly)

/** Renders a server-supplied Plotly figure, themed for the active mode.
    Sizing: `useResizeHandler` + `autosize` fits the chart to its container.
    We deliberately do NOT also set `config.responsive` — having both attaches
    two window-resize listeners, which compounds into a growth loop that makes
    charts visibly "zoom in" after a few resizes/tab switches.

    A hover download button exports the chart as a PNG via Plotly.downloadImage
    (the default modebar stays hidden to keep the chrome clean). */
/** Choose the entrance gesture from the figure's trace types so each chart kind
    reveals in a way that fits it: a line traces in, a scatter/bars fill up, a
    heatmap settles, a pie blooms. An explicit `reveal` prop overrides this. */
type Reveal = 'wipe' | 'rise' | 'settle' | 'bloom'
function pickReveal(fig: any): Reveal {
  const data: any[] = Array.isArray(fig?.data) ? fig.data : []
  if (!data.length) return 'wipe'
  if (data.some((d) => d?.type === 'pie')) return 'bloom'
  if (data.some((d) => d?.type === 'heatmap')) return 'settle'
  if (data.some((d) => d?.type === 'bar')) return 'rise'
  // scatter: markers-only (a point cloud, e.g. the IRR scatter) fills bottom-up;
  // anything with lines/fills (time series, fans) traces left-to-right.
  const pts = data.filter((d) => !d?.type || d.type === 'scatter' || d.type === 'scattergl')
  if (pts.length && pts.every((d) => typeof d.mode === 'string' && d.mode.includes('markers') && !d.mode.includes('lines'))) return 'rise'
  return 'wipe'
}

export default function Figure({ fig, height, name = 'chart', noDownload, reveal }: { fig: any; height?: number; name?: string; noDownload?: boolean; reveal?: Reveal }) {
  const { mode } = useTheme()
  const themed = useMemo(() => themeFigure(fig, mode), [fig, mode])
  const auto = useMemo(() => pickReveal(fig), [fig])
  const variant = reveal ?? auto
  const gd = useRef<any>(null)
  const [hover, setHover] = useState(false)

  // Export a clean, report-styled PNG: re-theme to the light palette (matching
  // the PDF charts) on a solid white canvas with generous margins, regardless of
  // the active UI mode — a dark-mode screen export would otherwise look nothing
  // like the report. Renders off-screen via toImage so the on-screen chart is
  // untouched.
  const download = async () => {
    const W = 1120, H = 640
    const light = themeFigure(fig, 'light')
    const hasTitle = !!light.layout?.title?.text
    const layout = {
      ...light.layout,
      paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff',
      width: W, height: H,
      margin: { l: 70, r: 32, t: hasTitle ? 66 : 36, b: 60 },
    }
    try {
      const url = await Plotly.toImage(
        { data: light.data, layout, config: { staticPlot: true } } as any,
        { format: 'png', width: W, height: H, scale: 2 },
      )
      const a = document.createElement('a')
      a.href = url; a.download = `${name}.png`
      document.body.appendChild(a); a.click(); a.remove()
    } catch (e) {
      console.warn('chart download failed', e)
    }
  }

  return (
    <div className={`chart-reveal chart-reveal--${variant}`} style={{ position: 'relative', width: '100%', height: height ?? '100%', minWidth: 0, overflow: 'hidden' }}
         onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      {!noDownload && <button onClick={download} title="Download PNG" aria-label="Download chart"
        style={{
          position: 'absolute', top: 6, right: 6, zIndex: 3, display: 'flex', alignItems: 'center',
          padding: 6, borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
          background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-muted)',
          opacity: hover ? 0.95 : 0, transition: 'opacity .15s ease', boxShadow: 'var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.08))',
        }}>
        <Icon name="download" size={15} />
      </button>}
      <Plot
        data={themed.data}
        layout={{ ...themed.layout, autosize: true, margin: themed.layout?.margin ?? { l: 48, r: 16, t: 28, b: 40 } }}
        config={{ displayModeBar: false }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
        onInitialized={(_: unknown, graphDiv: any) => { gd.current = graphDiv }}
      />
    </div>
  )
}
