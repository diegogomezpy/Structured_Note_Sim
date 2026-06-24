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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '8px 2px' }}>
      {stages.map((label, i) => {
        const state = i < step ? 'done' : i === step ? 'active' : 'todo'
        return (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{
              width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
              border: `2px solid ${state === 'todo' ? 'var(--border-strong)' : 'var(--accent)'}`,
              background: state === 'done' ? 'var(--accent)' : 'transparent',
              boxShadow: state === 'active' ? '0 0 0 4px var(--accent-weak)' : 'none',
              transition: 'all 0.2s ease',
            }} />
            <span style={{
              fontSize: 14,
              color: state === 'todo' ? 'var(--text-faint)' : 'var(--text)',
              fontWeight: state === 'active' ? 600 : 400,
            }}>
              {label}{state === 'active' ? '…' : ''}
            </span>
          </div>
        )
      })}
    </div>
  )
}
