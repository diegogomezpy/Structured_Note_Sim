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
            {([['', ''], ['S₀', 'calib_tip_s0'], ['μ p.a.', 'calib_tip_mu'], ['V₀ (σ)', 'calib_tip_v0'], ['θ (σ)', 'calib_tip_theta'], ['κ', 'calib_tip_kappa'], ['ξ', 'calib_tip_xi'], ['ρ', 'calib_tip_rho'], ['Feller', 'calib_tip_feller']] as const).map(([h, tip], i) => (
              <th key={i} title={tip ? t(tip) : undefined} style={{ ...th, textAlign: i === 0 ? 'left' : 'right', cursor: tip ? 'help' : undefined }}>
                {h}{tip ? <span style={{ color: 'var(--text-faint)', marginLeft: 3 }}>ⓘ</span> : ''}
              </th>
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

      {/* Always-visible guide to the Heston parameters (the column headers also
          carry these as hover tooltips). */}
      <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 9 }}>{t('calib_guide')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(270px, 1fr))', gap: '8px 22px' }}>
          {([['S₀', 'calib_tip_s0'], ['μ', 'calib_tip_mu'], ['V₀', 'calib_tip_v0'], ['θ', 'calib_tip_theta'], ['κ', 'calib_tip_kappa'], ['ξ', 'calib_tip_xi'], ['ρ', 'calib_tip_rho'], ['Feller', 'calib_tip_feller']] as const).map(([sym, tip]) => (
            <div key={sym} style={{ fontSize: 12, lineHeight: 1.5, display: 'flex', gap: 9 }}>
              <span className="mono" style={{ fontWeight: 600, color: 'var(--accent-text)', minWidth: 40, flexShrink: 0 }}>{sym}</span>
              <span style={{ color: 'var(--text-muted)' }}>{t(tip)}</span>
            </div>
          ))}
        </div>
      </div>

      {summary.t_dof != null && (
        <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 12 }}>
          {t('t_copula_dof')} {num(summary.t_dof, 1)}
        </div>
      )}
    </div>
  )
}
