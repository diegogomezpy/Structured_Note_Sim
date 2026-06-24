"""FastAPI backend for the Structured Note Simulator.

A thin API layer over the existing pure-quant core (`core/`, `data/`) that reuses
the Streamlit-free `app/charts.py` (figures → Plotly JSON), `app/pdf_report.py`,
`app/translations.py`, and `app/underlyings.py`. The React front-end (`web/`) is
the new UI; nothing numeric is reimplemented here.
"""
