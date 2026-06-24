import { useMemo } from 'react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'
import { useTheme } from '../theme/ThemeProvider'
import { themeFigure } from '../lib/plotlyTheme'

const Plot = createPlotlyComponent(Plotly)

/** Renders a server-supplied Plotly figure, themed for the active mode.
    Sizing: `useResizeHandler` + `autosize` fits the chart to its container.
    We deliberately do NOT also set `config.responsive` — having both attaches
    two window-resize listeners, which compounds into a growth loop that makes
    charts visibly "zoom in" after a few resizes/tab switches. */
export default function Figure({ fig, height }: { fig: any; height?: number }) {
  const { mode } = useTheme()
  const themed = useMemo(() => themeFigure(fig, mode), [fig, mode])
  return (
    <div style={{ width: '100%', height: height ?? '100%', minWidth: 0, overflow: 'hidden' }}>
      <Plot
        data={themed.data}
        layout={{ ...themed.layout, autosize: true, margin: themed.layout?.margin ?? { l: 48, r: 16, t: 28, b: 40 } }}
        config={{ displayModeBar: false }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </div>
  )
}
