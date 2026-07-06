/* Custom Plotly bundle — registers ONLY the trace types the app actually draws:
   bar, histogram, scatter (incl. filled fans), pie and heatmap (the px.imshow
   correlation matrices render as heatmap traces on a numeric zmin/zmax scale — NOT
   the `image` trace, which would drag in Node's buffer/ polyfill). Replacing
   plotly.js-dist-min with this modular build drops mapbox-gl / maplibre-gl / gl3d /
   and the rest of the unused trace zoo, cutting the bundle ~4×. Add a module here
   if a new chart type appears. */
import Plotly from 'plotly.js/lib/core'
import bar from 'plotly.js/lib/bar'
import histogram from 'plotly.js/lib/histogram'
import scatter from 'plotly.js/lib/scatter'
import pie from 'plotly.js/lib/pie'
import heatmap from 'plotly.js/lib/heatmap'

Plotly.register([bar, histogram, scatter, pie, heatmap])

export default Plotly
