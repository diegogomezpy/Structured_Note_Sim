import { useEffect, useRef, useState } from 'react'

/** Eases a numeric value up to `value` on mount/change. `format` controls the
    rendered string so we never display raw float artifacts. The figure counts to
    its new value rather than snapping (Motion · III); under prefers-reduced-motion
    it snaps. With `animateOnMount`, it counts up from 0 the first time it appears
    (results settling in after a run); otherwise it shows the value and only
    animates on later changes (e.g. a live ticker tick). */
export default function AnimatedNumber({
  value, format, duration = 700, animateOnMount = false,
}: { value: number; format: (n: number) => string; duration?: number; animateOnMount?: boolean }) {
  const [shown, setShown] = useState(animateOnMount ? 0 : value)
  const fromRef = useRef(animateOnMount ? 0 : value)
  const rafRef = useRef(0)

  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setShown(value); fromRef.current = value; return
    }
    const from = fromRef.current
    const start = performance.now()
    let done = false
    // Guarantee the final value even if rAF is throttled/never fires (some
    // headless/idle contexts), so a figure can never get stuck mid-count.
    const finish = () => { if (!done) { done = true; setShown(value); fromRef.current = value } }
    const tick = (now: number) => {
      if (done) return
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3) // easeOutCubic
      setShown(from + (value - from) * eased)
      if (p < 1) rafRef.current = requestAnimationFrame(tick)
      else finish()
    }
    rafRef.current = requestAnimationFrame(tick)
    const safety = setTimeout(finish, duration + 80)
    return () => { cancelAnimationFrame(rafRef.current); clearTimeout(safety) }
  }, [value, duration])

  return <>{format(shown)}</>
}
