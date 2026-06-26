import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import Icon from './Icon'

/** Lightweight toast notifications — Motion · V.
    Enter: slide in from the left (translateX −16px → 0) + fade, on the `enter`
    curve over 200ms. Exit: slide back out + fade on the `exit` curve over 160ms.
    A 3px accent border-left carries the tone. Auto-dismisses; reduced-motion is
    handled by the global CSS override (transitions collapse, so it just appears). */
export interface ToastInput { title: string; sub?: string; tone?: 'accent' | 'amber' | 'red'; icon?: 'check' | 'info' | 'download' }
interface ToastItem extends ToastInput { id: number }

const ToastCtx = createContext<{ push: (t: ToastInput) => void }>({ push: () => {} })
export const useToast = () => useContext(ToastCtx)

const TONE: Record<NonNullable<ToastInput['tone']>, string> = {
  accent: 'var(--accent)', amber: 'var(--amber)', red: 'var(--red)',
}
const VISIBLE_MS = 3600   // dwell before auto-dismiss
const EXIT_MS = 180       // matches --dur-base exit transition

function ToastCard({ item, onDone }: { item: ToastItem; onDone: (id: number) => void }) {
  const [leaving, setLeaving] = useState(false)
  const tone = TONE[item.tone ?? 'accent']

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
      display: 'flex', alignItems: 'center', gap: 11,
      background: 'var(--surface)', border: '1px solid var(--border)', borderLeft: `3px solid ${tone}`,
      borderRadius: 7, padding: '11px 14px', boxShadow: 'var(--shadow)', minWidth: 240, maxWidth: 360,
      // Enter as a CSS animation (resting at its final frame); on exit, drop the
      // animation and transition out so the slide reverses cleanly.
      ...(leaving
        ? { opacity: 0, transform: 'translateX(-16px)', transition: 'opacity var(--dur-base) var(--ease-exit), transform var(--dur-base) var(--ease-exit)' }
        : { animation: 'toastIn var(--dur-enter) var(--ease-enter) both' }),
    }}>
      <span style={{ display: 'flex', color: tone, flexShrink: 0 }}><Icon name={item.icon ?? 'check'} size={16} /></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)' }}>{item.title}</div>
        {item.sub && <div className="mono" style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.sub}</div>}
      </div>
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
