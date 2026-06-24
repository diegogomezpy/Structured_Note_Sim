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
export default function Figure({ fig, height, name = 'chart' }: { fig: any; height?: number; name?: string }) {
  const { mode } = useTheme()
  const themed = useMemo(() => themeFigure(fig, mode), [fig, mode])
  const gd = useRef<any>(null)
  const [hover, setHover] = useState(false)

  const download = () => {
    if (!gd.current) return
    const rect = gd.current.getBoundingClientRect?.() ?? { width: 1000, height: 560 }
    Plotly.downloadImage(gd.current, {
      format: 'png', filename: name,
      width: Math.max(900, Math.round(rect.width)), height: Math.max(500, Math.round(rect.height)), scale: 2,
    })
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: height ?? '100%', minWidth: 0, overflow: 'hidden' }}
         onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button onClick={download} title="Download PNG" aria-label="Download chart"
        style={{
          position: 'absolute', top: 6, right: 6, zIndex: 3, display: 'flex', alignItems: 'center',
          padding: 6, borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
          background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-muted)',
          opacity: hover ? 0.95 : 0, transition: 'opacity .15s ease', boxShadow: 'var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.08))',
        }}>
        <Icon name="download" size={15} />
      </button>
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
