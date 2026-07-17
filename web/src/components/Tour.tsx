import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useI18n } from '../i18n/I18nProvider'

/** A guided coachmark tour: a dim scrim with a spotlight cut around the target
    element and an anchored card (eyebrow · step counter · serif title · body ·
    progress dots · Skip/Back/Next), matching the reference design. Steps with no
    `target` render centered (intro/outro). Targets are CSS selectors — usually a
    `data-tour="…"` attribute on the element to highlight. A missing target
    degrades to a centered card so a tour never breaks if a screen isn't mounted. */
export interface TourStep {
  target?: string
  title: string
  body: string
  placement?: 'auto' | 'top' | 'bottom' | 'left' | 'right'
}

interface TourCtx { start: (steps: TourStep[]) => void; active: boolean }
const Ctx = createContext<TourCtx>({ start: () => {}, active: false })
export const useTour = () => useContext(Ctx)

/** The main onboarding tour, anchored to `data-tour="…"` landmarks. Steps whose
    target isn't on screen (e.g. results before a run) degrade to a centred card. */
export function mainTour(t: (k: string) => string): TourStep[] {
  return [
    { title: t('tour_welcome_t'), body: t('tour_welcome_b') },
    { target: '[data-tour="term-sheet"]', title: t('tour_termsheet_t'), body: t('tour_termsheet_b'), placement: 'right' },
    { target: '[data-tour="underlyings"]', title: t('tour_underlyings_t'), body: t('tour_underlyings_b'), placement: 'right' },
    // The rail no longer inlines the term/mechanic fields (they live in the
    // settings overlay), so the tour goes straight from the underlyings to it.
    { target: '[data-tour="settings"]', title: t('tour_settings_t'), body: t('tour_settings_b'), placement: 'right' },
    { target: '[data-tour="structure"]', title: t('tour_structure_t'), body: t('tour_structure_b') },
    { target: '[data-tour="run"]', title: t('tour_run_t'), body: t('tour_run_b'), placement: 'right' },
    { target: '[data-tour="tabs"]', title: t('tour_tabs_t'), body: t('tour_tabs_b') },
    { target: '[data-tour="ticker"]', title: t('tour_ticker_t'), body: t('tour_ticker_b'), placement: 'bottom' },
    { title: t('tour_done_t'), body: t('tour_done_b') },
  ]
}

/** The report-maker tour — a focused walkthrough of building & branding a PDF,
    launched from the "Tutorial" button on the Report tab. Targets are
    `data-tour="rep-…"` landmarks inside the report panel. */
export function reportTour(t: (k: string) => string): TourStep[] {
  return [
    { title: t('rtour_welcome_t'), body: t('rtour_welcome_b') },
    { target: '[data-tour="rep-presets"]', title: t('rtour_presets_t'), body: t('rtour_presets_b'), placement: 'bottom' },
    { target: '[data-tour="rep-sections"]', title: t('rtour_sections_t'), body: t('rtour_sections_b'), placement: 'top' },
    { target: '[data-tour="rep-branding"]', title: t('rtour_branding_t'), body: t('rtour_branding_b'), placement: 'top' },
    { target: '[data-tour="rep-photos"]', title: t('rtour_photos_t'), body: t('rtour_photos_b'), placement: 'top' },
    { target: '[data-tour="rep-metrics"]', title: t('rtour_metrics_t'), body: t('rtour_metrics_b'), placement: 'top' },
    { target: '[data-tour="rep-generate"]', title: t('rtour_generate_t'), body: t('rtour_generate_b'), placement: 'top' },
    { title: t('rtour_done_t'), body: t('rtour_done_b') },
  ]
}

const CARD_W = 326
const GAP = 14
const MARGIN = 12

type Rect = { left: number; top: number; width: number; height: number }

export function TourProvider({ children }: { children: ReactNode }) {
  const [steps, setSteps] = useState<TourStep[] | null>(null)
  const [i, setI] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const [cardPos, setCardPos] = useState<{ left: number; top: number } | null>(null)

  const start = useCallback((s: TourStep[]) => { if (s.length) { setSteps(s); setI(0) } }, [])
  const close = useCallback(() => { setSteps(null); setRect(null); setCardPos(null) }, [])

  const step = steps?.[i] ?? null

  // Locate + spotlight the target for the current step, then keep tracking it on
  // scroll/resize. Keyed on `i` (and steps): the target element is captured in
  // this effect's closure so a stale measurement from the previous step can never
  // overwrite the current one. We avoid requestAnimationFrame (throttled when the
  // tab is idle, which would leave the spotlight unplaced).
  useLayoutEffect(() => {
    if (!steps) return
    const st = steps[i]
    const el = st?.target ? document.querySelector(st.target) as HTMLElement | null : null
    if (!el) { setRect(null); return }
    const measure = () => {
      const r = el.getBoundingClientRect()
      setRect({ left: r.left, top: r.top, width: r.width, height: r.height })
    }
    el.scrollIntoView({ block: 'center', behavior: 'auto' })
    measure()
    const id = setTimeout(measure, 90)
    window.addEventListener('scroll', measure, true)
    window.addEventListener('resize', measure)
    return () => {
      clearTimeout(id)
      window.removeEventListener('scroll', measure, true)
      window.removeEventListener('resize', measure)
    }
  }, [i, steps])

  // Position the card against the spotlight (or centre it when there's no target).
  useLayoutEffect(() => {
    if (!steps) return
    const ch = cardRef.current?.offsetHeight ?? 200
    const vw = window.innerWidth, vh = window.innerHeight
    if (!rect) { setCardPos({ left: (vw - CARD_W) / 2, top: Math.max(MARGIN, (vh - ch) / 2) }); return }
    const place4 = step?.placement ?? 'auto'
    const below = rect.top + rect.height + GAP + ch < vh
    const useBelow = place4 === 'bottom' || (place4 === 'auto' && (below || rect.top - ch - GAP < MARGIN))
    let top = useBelow ? rect.top + rect.height + GAP : rect.top - ch - GAP
    let left = rect.left + rect.width / 2 - CARD_W / 2
    // Side placement when there's room and the element is tall.
    if (place4 === 'left') { left = rect.left - CARD_W - GAP; top = rect.top }
    if (place4 === 'right') { left = rect.left + rect.width + GAP; top = rect.top }
    left = Math.max(MARGIN, Math.min(left, vw - CARD_W - MARGIN))
    top = Math.max(MARGIN, Math.min(top, vh - ch - MARGIN))
    setCardPos({ left, top })
  }, [rect, steps, i, step])

  // Glide the spotlight/card only when MOVING BETWEEN STEPS — never while the user
  // scrolls (the CSS transition would otherwise lag the highlight behind the page).
  const [animating, setAnimating] = useState(false)
  useEffect(() => {
    if (!steps) return
    setAnimating(true)
    const id = setTimeout(() => setAnimating(false), 320)
    return () => clearTimeout(id)
  }, [i, steps])

  // Keyboard: Esc closes, ←/→ navigate.
  useEffect(() => {
    if (!steps) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowRight') setI((n) => Math.min(steps.length - 1, n + 1))
      else if (e.key === 'ArrowLeft') setI((n) => Math.max(0, n - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [steps, close])

  return (
    <Ctx.Provider value={{ start, active: !!steps }}>
      {children}
      {steps && step && createPortal(
        <TourOverlay
          step={step} index={i} total={steps.length} rect={rect} cardPos={cardPos} cardRef={cardRef} animating={animating}
          onSkip={close} onBack={() => setI((n) => Math.max(0, n - 1))}
          onNext={() => (i + 1 >= steps.length ? close() : setI((n) => n + 1))}
        />,
        document.body,
      )}
    </Ctx.Provider>
  )
}

function TourOverlay({ step, index, total, rect, cardPos, cardRef, animating, onSkip, onBack, onNext }: {
  step: TourStep; index: number; total: number; rect: Rect | null
  cardPos: { left: number; top: number } | null; cardRef: React.RefObject<HTMLDivElement | null>
  animating: boolean
  onSkip: () => void; onBack: () => void; onNext: () => void
}) {
  const { t } = useI18n()
  const last = index + 1 >= total
  // Transition only between steps; `none` during scroll so the highlight tracks 1:1.
  const glide = animating ? undefined : ('none' as const)
  return (
    <>
      <div className="tour-block" onClick={onSkip} />
      {rect
        ? <div className="tour-spot" style={{ left: rect.left - 6, top: rect.top - 6, width: rect.width + 12, height: rect.height + 12, transition: glide }} />
        : <div className="tour-dim" />}
      <div ref={cardRef} className="tour-card" style={{ left: cardPos?.left ?? -9999, top: cardPos?.top ?? -9999, width: CARD_W, visibility: cardPos ? 'visible' : 'hidden', transition: glide }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span className="mono" style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent-text)' }}>{t('tour_eyebrow')}</span>
          <span className="mono" style={{ fontSize: 11, color: 'var(--text-faint)' }}>{index + 1} / {total}</span>
        </div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em', color: 'var(--text)', marginBottom: 7 }}>{step.title}</div>
        <div style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--text-muted)' }}>{step.body}</div>
        <div style={{ display: 'flex', gap: 5, margin: '16px 0 14px' }}>
          {Array.from({ length: total }).map((_, n) => (
            <span key={n} style={{ width: n === index ? 16 : 6, height: 6, borderRadius: 3, background: n === index ? 'var(--accent)' : 'var(--border-strong)', transition: 'width .2s var(--ease-settle)' }} />
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button onClick={onSkip} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5, color: 'var(--text-faint)', padding: 0 }}>{t('tour_skip')}</button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {index > 0 && <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5, color: 'var(--text-muted)', padding: 0 }}>{t('tour_back')}</button>}
            <button className="btn btn--primary" style={{ padding: '7px 16px' }} onClick={onNext}>{last ? t('tour_done') : t('tour_next')}</button>
          </div>
        </div>
      </div>
    </>
  )
}
