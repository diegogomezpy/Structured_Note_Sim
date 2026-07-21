import Plotly from './plotly'
import { themeFigure } from './plotlyTheme'

/** Render a Plotly figure to a clean, report-styled PNG data-URL: the light
    palette (matching the PDF charts) on a solid white canvas with generous
    margins, regardless of the active UI mode. Used by the per-chart download
    button and to embed the path-explorer selection into the PDF report so the
    figure in the report matches the on-screen chart exactly. Returns '' on
    failure. */
export async function figureToReportPng(fig: any, w = 1120, h = 640): Promise<string> {
  if (!fig || !Array.isArray(fig.data)) return ''
  const light = themeFigure(fig, 'light')
  const hasTitle = !!light.layout?.title?.text
  const layout = {
    ...light.layout,
    paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff',
    width: w, height: h,
    margin: { l: 70, r: 32, t: hasTitle ? 66 : 36, b: 60 },
  }
  try {
    return await Plotly.toImage(
      { data: light.data, layout, config: { staticPlot: true } } as any,
      { format: 'png', width: w, height: h, scale: 2 },
    )
  } catch (e) {
    console.warn('figureToReportPng failed', e)
    return ''
  }
}
