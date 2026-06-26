import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export interface TabDef {
  id: string
  label: ReactNode
  disabled?: boolean
}

/** Tab row with a single underline that *slides* (left + width) between tabs
    rather than each tab carrying its own border — Motion · VI. The indicator is
    measured from the active button's box, re-measured on resize/reflow (e.g.
    when fonts load or the language changes). */
export default function Tabs({
  tabs, active, onChange,
}: { tabs: TabDef[]; active: string; onChange: (id: string) => void }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [ind, setInd] = useState<{ left: number; width: number }>({ left: 0, width: 0 })

  const measure = () => {
    const wrap = wrapRef.current
    if (!wrap) return
    const el = wrap.querySelector<HTMLButtonElement>(`[data-tab="${CSS.escape(active)}"]`)
    if (!el) return
    const left = el.offsetLeft
    const width = el.offsetWidth
    // Guard: only update when the geometry actually changed, so the layout
    // effect (which runs on every render) can't loop on a fresh object.
    setInd((prev) => (prev.left === left && prev.width === width ? prev : { left, width }))
  }

  useLayoutEffect(measure)

  useEffect(() => {
    const wrap = wrapRef.current
    if (!wrap || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div ref={wrapRef} style={{ position: 'relative', display: 'flex', gap: 2, borderBottom: '1px solid var(--border)' }}>
      {tabs.map((tab) => {
        const on = tab.id === active
        return (
          <button key={tab.id} data-tab={tab.id} disabled={tab.disabled} onClick={() => onChange(tab.id)}
            style={{
              border: 'none', background: 'transparent', cursor: tab.disabled ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit', fontSize: 13.5, fontWeight: on ? 600 : 400, padding: '10px 16px',
              color: tab.disabled ? 'var(--text-faint)' : on ? 'var(--accent-text)' : 'var(--text-muted)',
              transition: 'color var(--dur-base) var(--ease-settle)',
            }}>
            {tab.label}
          </button>
        )
      })}
      <div aria-hidden style={{
        position: 'absolute', bottom: -1, height: 2, background: 'var(--accent)', borderRadius: 1,
        left: ind.left, width: ind.width,
        transition: 'left var(--dur-base) var(--ease-settle), width var(--dur-base) var(--ease-settle)',
      }} />
    </div>
  )
}
