import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useI18n } from '../../i18n/I18nProvider'
import Icon from '../Icon'
import type { Branding, NoteTerms } from '../../api/types'

/* The proof: the REAL report, rendered by the server and shown page by page.

   This is not a mock of the PDF — it is the PDF. The pages come from the same
   `_build_pdf_report` that produces the file you download, so "what you see is
   what you get" holds by construction instead of by keeping a second
   implementation in sync. The hand-written DOM preview it replaces drifted
   constantly, and every "the preview and the real thing look nothing alike"
   report traced back to that.

   Cost of the truthful version: a render is a round-trip rather than instant.
   Three things keep it usable —
     * debounce, so a slider drag issues one render and not forty;
     * abort in-flight, so responses cannot land out of order and settle the
       canvas on a stale page;
     * keep showing the last good pages, dimmed, while the next render is in
       flight — never blank, never a spinner over emptiness.

   Figures are placeholders on purpose. Kaleido costs ~2s per chart regardless
   of resolution, which would make this unusable; every other surface — covers,
   mastheads, section heads, dividers, tables, type, logos, watermark — is
   genuine. The bar says so rather than letting the grey blocks look like a bug.
*/

const A4 = 297 / 210          // page aspect, for the placeholder boxes

/* Long enough to sit through a burst of input. A number spinner clicked
   repeatedly, a colour dragged, a chamfer nudged 0.5mm at a time — each of
   those should produce ONE render when you stop, not one per step. 700ms is
   past the gap between deliberate clicks but still feels immediate when you
   change one thing and look up. */
const DEBOUNCE_MS = 700

type Status = 'idle' | 'chrome' | 'charts' | 'ok' | 'error'

export default function ProofCanvas({ brand, terms, lang, zoom }: {
  brand: Branding
  terms: NoteTerms | null
  lang: string
  zoom: number
}) {
  const { t } = useI18n()
  const [pages, setPages] = useState<string[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const [ms, setMs] = useState(0)
  const abortRef = useRef<AbortController | null>(null)

  // Re-render whenever anything the PDF reads changes. Serialising the brand is
  // the honest dependency: it is what the server is handed, so any field that
  // affects the document — including ones no control has yet — triggers a
  // refresh without needing to be enumerated here.
  const dep = JSON.stringify([brand, terms?.name, terms?.tickers, lang])

  useEffect(() => {
    const timer = setTimeout(() => {
      abortRef.current?.abort()
      const ac = new AbortController()
      abortRef.current = ac
      const t0 = performance.now()
      const show = (r: { pages: string[] }) =>
        setPages(r.pages.map((b64) => `data:image/png;base64,${b64}`))

      // Two passes. The first stubs the charts and lands in ~0.3s, so the
      // layout, type and colour are on screen almost immediately. The second
      // draws the real charts and swaps them in — Kaleido costs ~2s per figure,
      // so waiting for it before showing anything would make every edit feel
      // broken. Page geometry is identical between the two (the stub is drawn
      // at each figure's true size), so the swap does not reflow.
      setStatus('chrome')
      api.reportProof({ branding: brand, terms, lang, scale: 1.4, figures: 'stub' }, ac.signal)
        .then((r) => {
          if (ac.signal.aborted) return
          show(r)
          setMs(Math.round(performance.now() - t0))
          setStatus('charts')
          setError('')
          return api.reportProof(
            { branding: brand, terms, lang, scale: 1.4, figures: 'real' }, ac.signal)
        })
        .then((r) => {
          if (!r || ac.signal.aborted) return
          show(r)
          setMs(Math.round(performance.now() - t0))
          setStatus('ok')
        })
        .catch((e: Error) => {
          if (ac.signal.aborted || e.name === 'AbortError') return
          setError(e.message)
          setStatus('error')
        })
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dep])

  useEffect(() => () => abortRef.current?.abort(), [])

  const busy = status === 'chrome' || status === 'charts'
  const stale = status === 'chrome' && pages.length > 0
  const width = Math.round(520 * zoom)

  return (
    <div className="proof">
      <div className="proof__bar">
        <span className={`proof__dot proof__dot--${busy ? 'loading' : status}`} aria-hidden />
        <span className="proof__state">
          {status === 'chrome' ? t('proof_rendering')
            : status === 'error' ? t('proof_failed')
              : status === 'idle' ? t('proof_idle')
                : t('proof_pages').replace('{n}', String(pages.length)) + ` · ${ms}ms`}
        </span>
        {status === 'charts' && <span className="proof__note">{t('proof_drawing_charts')}</span>}
      </div>

      {status === 'error' && (
        <div className="proof__error">
          <Icon name="info" size={14} /> {error}
        </div>
      )}

      <div className="proof__stack" style={{ opacity: stale ? 0.45 : 1 }}>
        {pages.length === 0 && status !== 'error' ? (
          // Skeletons at true A4 aspect, so the layout does not jump when the
          // first real render lands.
          [0, 1].map((i) => (
            <div key={i} className="skeleton proof__page"
                 style={{ width, height: Math.round(width * A4) }} />
          ))
        ) : (
          pages.map((src, i) => (
            <figure key={i} className="proof__page-wrap">
              <img src={src} alt={t('proof_page_alt').replace('{n}', String(i + 1))}
                   className="proof__page" style={{ width }} loading="lazy" />
              <figcaption className="proof__num">{i + 1}</figcaption>
            </figure>
          ))
        )}
      </div>
    </div>
  )
}
