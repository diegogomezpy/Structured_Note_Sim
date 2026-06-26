import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import Icon from './Icon'

/** Centered modal overlay. Closes on Escape or backdrop click; locks body
    scroll while open. Sticky header + optional sticky footer; the body scrolls.
    Enter motion (Motion · V): scrim fades (.modal-scrim, base/settle), card rises
    8px + scales from .98 (.modal-card, enter) — both as CSS animations. */
export default function Modal({
  title, onClose, children, footer, width = 980,
}: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: number }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose])

  return createPortal((
    <div
      className="modal-scrim"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(20, 28, 23, 0.46)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: '4vh 16px', overflow: 'auto',
      }}>
      <div className="modal-card" style={{
        background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        boxShadow: 'var(--shadow)', width: `min(${width}px, 100%)`, maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
      }}>
        <header style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
          padding: '16px 22px', borderBottom: '1px solid var(--border)', flexShrink: 0,
        }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, fontWeight: 600, letterSpacing: '-0.01em' }}>{title}</div>
          <button className="btn btn--ghost" onClick={onClose} aria-label="Close" style={{ padding: 7 }}>
            <Icon name="x" size={17} />
          </button>
        </header>

        <div style={{ overflow: 'auto', padding: '20px 22px' }}>{children}</div>

        {footer && (
          <footer style={{
            display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10,
            padding: '14px 22px', borderTop: '1px solid var(--border)', flexShrink: 0,
          }}>{footer}</footer>
        )}
      </div>
    </div>
  ), document.body)
}
