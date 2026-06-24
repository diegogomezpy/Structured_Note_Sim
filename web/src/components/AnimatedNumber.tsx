import { useEffect, useRef, useState } from 'react'

/** Eases a numeric value up to `value` on mount/change. `format` controls the
    rendered string so we never display raw float artifacts. */
export default function AnimatedNumber({
  value, format, duration = 650,
}: { value: number; format: (n: number) => string; duration?: number }) {
  const [shown, setShown] = useState(value)
  const fromRef = useRef(value)
  const rafRef = useRef(0)

  useEffect(() => {
    const from = fromRef.current
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3) // easeOutCubic
      setShown(from + (value - from) * eased)
      if (p < 1) rafRef.current = requestAnimationFrame(tick)
      else fromRef.current = value
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [value, duration])

  return <>{format(shown)}</>
}
