import { useI18n } from '../i18n/I18nProvider'
import TickerLogo from './TickerLogo'
import { pct, num } from '../lib/format'
import type { SimSummary } from '../api/types'

const th: React.CSSProperties = {
  textAlign: 'right', padding: '8px 14px', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.05em',
  textTransform: 'uppercase', color: 'var(--text-muted)', borderBottom: '1px solid var(--border)',
}
const td: React.CSSProperties = { padding: '8px 14px', textAlign: 'right', borderBottom: '1px solid var(--border)' }

export function AutocallByPeriodTable({ summary, autocallStart }: { summary: SimSummary; autocallStart: number }) {
  const { t } = useI18n()
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead><tr>
          <th style={{ ...th, textAlign: 'left' }}>{t('col_period')}</th>
          <th style={th}>{t('col_time')}</th>
          <th style={th}>{t('col_p_autocall')}</th>
          <th style={{ ...th, textAlign: 'right' }}>{t('col_eligible')}</th>
        </tr></thead>
        <tbody>
          {summary.autocall_by_period.map((p, i) => {
            const eligible = i + 1 >= autocallStart
            return (
              <tr key={i}>
                <td className="mono" style={{ ...td, textAlign: 'left' }}>P{i + 1}</td>
                <td className="mono" style={{ ...td, color: 'var(--text-muted)' }}>{num(summary.obs_times[i], 2)}</td>
                <td className="mono" style={td}>{pct(p, 2)}</td>
                <td style={{ ...td, color: eligible ? 'var(--text)' : 'var(--text-faint)' }}>
                  {eligible ? t('yes') : t('coupon_only')}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function CalibrationTable({ summary, nameToSym }: { summary: SimSummary; nameToSym: Record<string, string> }) {
  const { t } = useI18n()
  const sig = (v: number | null) => (v == null ? '—' : `${num(Math.sqrt(Math.abs(v)) * 100, 0)}%`)
  return (
    <div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, whiteSpace: 'nowrap' }}>
          <thead><tr>
            {['', 'S₀', 'μ p.a.', 'V₀ (σ)', 'θ (σ)', 'κ', 'ξ', 'ρ', 'Feller'].map((h, i) => (
              <th key={i} style={{ ...th, textAlign: i === 0 ? 'left' : 'right' }}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {summary.calibration.map((c) => {
              const ok = (c.feller ?? 0) >= 0
              return (
                <tr key={c.name}>
                  <td style={{ ...td, textAlign: 'left' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                      <TickerLogo symbol={nameToSym[c.name] ?? c.name} name={c.name} size={16} />{c.name}
                    </span>
                  </td>
                  <td className="mono" style={td}>{num(c.S0, 2)}</td>
                  <td className="mono" style={{ ...td, color: (c.mu ?? 0) >= 0 ? 'var(--text)' : 'var(--red)' }}>{pct(c.mu, 1)}</td>
                  <td className="mono" style={td}>{sig(c.V0)}</td>
                  <td className="mono" style={td}>{sig(c.theta)}</td>
                  <td className="mono" style={td}>{num(c.kappa, 2)}</td>
                  <td className="mono" style={td}>{num(c.xi, 2)}</td>
                  <td className="mono" style={td}>{num(c.rho, 3)}</td>
                  <td style={td}>
                    <span className="pill" style={{ background: ok ? 'var(--green-weak)' : 'var(--amber-weak)', color: ok ? 'var(--green)' : 'var(--amber)' }}>
                      {ok ? t('feller_ok') : t('feller_warn')}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {summary.t_dof != null && (
        <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 10 }}>
          {t('t_copula_dof')} {num(summary.t_dof, 1)}
        </div>
      )}
    </div>
  )
}
