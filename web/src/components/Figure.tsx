import { useMemo } from 'react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'
import { useTheme } from '../theme/ThemeProvider'
import { themeFigure } from '../lib/plotlyTheme'

const Plot = createPlotlyComponent(Plotly)

/** Renders a server-supplied Plotly figure, themed for the active mode. */
export default function Figure({ fig, height }: { fig: any; height?: number }) {
  const { mode } = useTheme()
  const themed = useMemo(() => themeFigure(fig, mode), [fig, mode])
  return (
    <Plot
      data={themed.data}
      layout={{ ...themed.layout, autosize: true, margin: themed.layout?.margin ?? { l: 48, r: 16, t: 28, b: 40 } }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height: height ?? '100%' }}
      useResizeHandler
    />
  )
}
