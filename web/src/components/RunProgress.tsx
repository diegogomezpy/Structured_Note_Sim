import { useEffect, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'

/** Staged "working" indicator. The backend POST is atomic (no streaming), so we
    advance through calibrate → simulate → price on a timer to communicate
    liveness; it settles on the last stage until the response returns. */
export default function RunProgress() {
  const { t } = useI18n()
  const stages = [t('calibrating'), t('simulating'), t('pricing')]
  const [step, setStep] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, stages.length - 1)), 1100)
    return () => clearInterval(id)
  }, [stages.length])

  // Mercator running state: serif heading + a determinate 3px hairline bar +
  // a mono telemetry line. No spinner.
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '6px 2px' }}>
      <div style={{ fontFamily: 'var(--font-serif)', fontWeight: 600, fontSize: 16, letterSpacing: '-0.01em' }}>
        {stages[step]}…
      </div>
      <div style={{ height: 3, borderRadius: 999, background: 'var(--border)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${((step + 1) / stages.length) * 100}%`,
          background: 'var(--accent)', borderRadius: 999, transition: 'width 0.5s var(--ease-enter)',
        }} />
      </div>
      <div className="mono" style={{ fontSize: 11, letterSpacing: '0.04em', display: 'flex', gap: 7, flexWrap: 'wrap' }}>
        {stages.map((label, i) => (
          <span key={label} style={{ color: i === step ? 'var(--accent-text)' : i < step ? 'var(--text-muted)' : 'var(--text-faint)' }}>
            {label.toLowerCase()}{i < stages.length - 1 ? ' ·' : ''}
          </span>
        ))}
      </div>

      {/* Skeleton metric cards in the panel's own shapes (States doc) — they
          shimmer where the hero figures will land. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginTop: 10 }}>
        {[0, 1, 2].map((i) => (
          <div key={i} className="card" style={{ padding: '18px 20px', boxShadow: 'none' }}>
            <div className="skeleton" style={{ height: 9, width: '55%', marginBottom: 16 }} />
            <div className="skeleton" style={{ height: 26, width: '78%' }} />
          </div>
        ))}
      </div>
    </div>
  )
}
