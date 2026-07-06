// Modular Plotly entrypoints ship no bundled TS types — declare them loosely
// (the app drives Plotly with plain JSON figures, so `any` is fine here).
declare module 'plotly.js/lib/core' {
  const Plotly: any
  export default Plotly
}
declare module 'plotly.js/lib/*' {
  const traceModule: any
  export default traceModule
}
declare module 'react-plotly.js/factory' {
  import type { ComponentType } from 'react'
  // react-plotly.js props are loosely typed here; we drive it with plain JSON.
  const createPlotlyComponent: (plotly: unknown) => ComponentType<any>
  export default createPlotlyComponent
}
