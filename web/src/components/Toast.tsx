import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import Icon from './Icon'

/** Lightweight toast notifications — Motion · V.
    Enter: slide in from the left (translateX −16px → 0) + fade, on the `enter`
    curve over 200ms. Exit: slide back out + fade on the `exit` curve over 160ms.
    A 3px accent border-left carries the tone. Auto-dismisses; reduced-motion is
    handled by the global CSS override (transitions collapse, so it just appears). */
export interface ToastInput {
  title: string; sub?: string
  tone?: 'accent' | 'amber' | 'red' | 'ink'
  icon?: 'check' | 'info' | 'download' | 'refresh'
  action?: { label: string; onClick: () => void }
}
interface ToastItem extends ToastInput { id: number }

const ToastCtx = createContext<{ push: (t: ToastInput) => void }>({ push: () => {} })
export const useToast = () => useContext(ToastCtx)

const TONE: Record<NonNullable<ToastInput['tone']>, string> = {
  accent: 'var(--accent)', amber: 'var(--amber)', red: 'var(--red)', ink: '#7eb4a0',
}
const VISIBLE_MS = 3600   // dwell before auto-dismiss
const EXIT_MS = 180       // matches --dur-base exit transition

function ToastCard({ item, onDone }: { item: ToastItem; onDone: (id: number) => void }) {
  const [leaving, setLeaving] = useState(false)
  const ink = item.tone === 'ink'
  const tone = TONE[item.tone ?? 'accent']
  const dismiss = () => setLeaving(true)

  useEffect(() => {
    const hideT = setTimeout(() => setLeaving(true), VISIBLE_MS)
    return () => clearTimeout(hideT)
  }, [])

  useEffect(() => {
    if (!leaving) return
    const t = setTimeout(() => onDone(item.id), EXIT_MS)
    return () => clearTimeout(t)
  }, [leaving, item.id, onDone])

  return (
    <div role="status" style={{
      display: 'flex', alignItems: 'center', gap: 11, pointerEvents: 'auto',
      background: ink ? '#1c241f' : 'var(--surface)',
      border: ink ? 'none' : '1px solid var(--border)',
      borderLeft: ink ? undefined : `3px solid ${tone}`,
      borderRadius: 7, padding: '11px 14px', boxShadow: 'var(--shadow)', minWidth: 240, maxWidth: 360,
      // Enter as a CSS animation (resting at its final frame); on exit, drop the
      // animation and transition out so the slide reverses cleanly.
      ...(leaving
        ? { opacity: 0, transform: 'translateX(-16px)', transition: 'opacity var(--dur-base) var(--ease-exit), transform var(--dur-base) var(--ease-exit)' }
        : { animation: 'toastIn var(--dur-enter) var(--ease-enter) both' }),
    }}>
      <span style={{ display: 'flex', color: tone, flexShrink: 0 }}><Icon name={item.icon ?? 'check'} size={16} /></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: ink ? '#f7f5ef' : 'var(--text)' }}>{item.title}</div>
        {item.sub && <div className="mono" style={{ fontSize: 10.5, color: ink ? '#b9c2bb' : 'var(--text-faint)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.sub}</div>}
      </div>
      {item.action ? (
        <button onClick={() => { item.action!.onClick(); dismiss() }}
          style={{ flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 11.5, fontWeight: 600, color: tone }}>
          {item.action.label}
        </button>
      ) : (
        <button onClick={dismiss} aria-label="Dismiss"
          style={{ flexShrink: 0, display: 'flex', background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: ink ? '#8c9189' : 'var(--text-faint)' }}>
          <Icon name="x" size={14} />
        </button>
      )}
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const idRef = useRef(0)
  const push = useCallback((t: ToastInput) => {
    setItems((prev) => [...prev, { ...t, id: (idRef.current += 1) }])
  }, [])
  const remove = useCallback((id: number) => setItems((prev) => prev.filter((x) => x.id !== id)), [])

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      {createPortal(
        <div style={{ position: 'fixed', left: 18, bottom: 18, zIndex: 1200, display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: 'none' }}>
          {items.map((it) => <ToastCard key={it.id} item={it} onDone={remove} />)}
        </div>,
        document.body,
      )}
    </ToastCtx.Provider>
  )
}
