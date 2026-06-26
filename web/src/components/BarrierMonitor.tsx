import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import { pct, pctSigned } from '../lib/format'

/** Barrier monitor — Mercator · Elements. A rust→ochre→viridian band with a rust
    tick at the knock-in level and a viridian marker at the live worst-of, so the
    distance to the barrier reads at a glance. All values are real (LiveResult). */
export default function BarrierMonitor({ now, barrier }: { now: number; barrier: number }) {
  const { t } = useI18n()
  const LO = 0.4, HI = 1.2   // band domain (40%–120% of strike)
  const clamp = (v: number) => Math.min(100, Math.max(0, ((v - LO) / (HI - LO)) * 100))
  const bp = clamp(barrier), np = clamp(now)
  const buffer = now - barrier
  const safe = buffer >= 0

  return (
    <Panel pad={18}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 18 }}>
        <span className="section-label">{t('live_wo_vs_barrier')}</span>
        <span className="mono" style={{ fontSize: 20, fontWeight: 600, color: safe ? 'var(--accent)' : 'var(--red)' }}>{pctSigned(buffer, 1)}</span>
      </div>
      <div style={{ position: 'relative', height: 8, marginBottom: 9 }}>
        <div className="grow-x" style={{
          position: 'absolute', inset: 0, borderRadius: 999,
          background: `linear-gradient(90deg, var(--red-weak) 0%, var(--amber-weak) ${bp}%, var(--accent-weak) 100%)`,
        }} />
        <div style={{ position: 'absolute', left: `${bp}%`, top: -4, bottom: -4, width: 1.5, background: 'var(--red)' }} />
        <div style={{
          position: 'absolute', left: `${np}%`, top: '50%', transform: 'translate(-50%, -50%)',
          width: 13, height: 13, borderRadius: '50%', background: 'var(--accent)',
          boxShadow: '0 0 0 3px var(--surface), 0 0 0 4px var(--accent-weak)',
        }} />
      </div>
      <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-faint)' }}>
        <span style={{ color: 'var(--red)' }}>{t('live_barrier')} {pct(barrier, 0)}</span>
        <span>{t('live_now')} {pct(now, 1)}</span>
        <span>{t('live_initial')} 100%</span>
      </div>
    </Panel>
  )
}
