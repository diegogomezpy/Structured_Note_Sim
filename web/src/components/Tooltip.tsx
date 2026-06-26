import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

const GAP = 9
const MARGIN = 8

/** Mercator tooltip — an ink card with a serif title and a Hanken body, for term
    help (Elements · 11). Rendered through a portal and positioned against the
    trigger so it is never clipped by a card's overflow. Shows on hover or
    keyboard focus; closes on leave/blur/scroll. The trigger is whatever you wrap
    (a label, an info dot, a metric). */
export function Tooltip({ title, body, children, disabled }: {
  title?: string
  body: ReactNode
  children: ReactNode
  disabled?: boolean
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ left: number; top: number; caret: number; below: boolean } | null>(null)

  useLayoutEffect(() => {
    if (!open || !ref.current || !cardRef.current) return
    const t = ref.current.getBoundingClientRect()
    const c = cardRef.current.getBoundingClientRect()
    const vw = window.innerWidth, vh = window.innerHeight
    const center = t.left + t.width / 2
    const left = Math.max(MARGIN, Math.min(center - c.width / 2, vw - c.width - MARGIN))
    const below = t.top - c.height - GAP < MARGIN && t.bottom + c.height + GAP < vh
    const top = below ? t.bottom + GAP : t.top - c.height - GAP
    const caret = Math.max(12, Math.min(center - left, c.width - 12))
    setPos({ left, top, caret, below })
  }, [open])

  // A brief hover/focus is enough; any scroll detaches the anchor, so just close.
  useLayoutEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    window.addEventListener('scroll', close, true)
    return () => window.removeEventListener('scroll', close, true)
  }, [open])

  if (disabled) return <>{children}</>

  return (
    <span
      ref={ref}
      style={{ display: 'inline-flex', alignItems: 'center' }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => { setOpen(false); setPos(null) }}
      onFocus={() => setOpen(true)}
      onBlur={() => { setOpen(false); setPos(null) }}
    >
      {children}
      {open && createPortal(
        <div
          ref={cardRef}
          role="tooltip"
          className="mtip"
          style={pos
            ? { left: pos.left, top: pos.top }
            : { left: -9999, top: -9999, visibility: 'hidden' }}
        >
          {title && <div className="mtip-title">{title}</div>}
          <div className="mtip-body">{body}</div>
          {pos && (
            <span
              className="mtip-caret"
              style={pos.below
                ? { top: -4, left: pos.caret - 4 }
                : { bottom: -4, left: pos.caret - 4 }}
            />
          )}
        </div>,
        document.body,
      )}
    </span>
  )
}

/** A small info dot that reveals a Tooltip on hover/focus — for labels and table
    headers where a help affordance should sit inline. */
export function InfoDot({ title, body }: { title?: string; body: ReactNode }) {
  return (
    <Tooltip title={title} body={body}>
      <button type="button" className="info-dot" aria-label={title ?? (typeof body === 'string' ? body : 'Info')}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v5M12 7.6h.01" />
        </svg>
      </button>
    </Tooltip>
  )
}
