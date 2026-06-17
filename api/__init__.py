"""FastAPI backend for the Structured Note Simulator.

Wraps the existing pure-quant library (`core/`, `data/`) and the chart/PDF
builders (`app/charts.py`, `app/pdf_report.py`) behind a JSON API so a static
front-end (e.g. GitHub Pages) can drive the simulator without Streamlit. The
Streamlit app remains the reference UI; this layer only *reads* shared code.
"""
