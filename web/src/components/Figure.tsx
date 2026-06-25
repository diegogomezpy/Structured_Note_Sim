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
export default function Figure({ fig, height, name = 'chart', noDownload }: { fig: any; height?: number; name?: string; noDownload?: boolean }) {
  const { mode } = useTheme()
  const themed = useMemo(() => themeFigure(fig, mode), [fig, mode])
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
    <div style={{ position: 'relative', width: '100%', height: height ?? '100%', minWidth: 0, overflow: 'hidden' }}
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
