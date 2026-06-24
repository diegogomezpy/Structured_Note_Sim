declare module 'plotly.js-dist-min'
declare module 'react-plotly.js/factory' {
  import type { ComponentType } from 'react'
  // react-plotly.js props are loosely typed here; we drive it with plain JSON.
  const createPlotlyComponent: (plotly: unknown) => ComponentType<any>
  export default createPlotlyComponent
}
