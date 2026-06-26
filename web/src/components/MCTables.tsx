import { useI18n } from '../i18n/I18nProvider'
import TickerLogo from './TickerLogo'
import { pct, num } from '../lib/format'
import type { SimSummary } from '../api/types'

export function AutocallByPeriodTable({ summary, autocallStart }: { summary: SimSummary; autocallStart: number }) {
  const { t } = useI18n()
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="ledger">
        <thead><tr>
          <th>{t('col_period')}</th>
          <th className="num">{t('col_time')}</th>
          <th className="num">{t('col_p_autocall')}</th>
          <th className="num">{t('col_eligible')}</th>
        </tr></thead>
        <tbody>
          {summary.autocall_by_period.map((p, i) => {
            const eligible = i + 1 >= autocallStart
            return (
              <tr key={i}>
                <td>P{i + 1}</td>
                <td className="num" style={{ color: 'var(--text-muted)' }}>{num(summary.obs_times[i], 2)}</td>
                <td className="num">{pct(p, 2)}</td>
                <td className="num" style={{ color: eligible ? 'var(--text)' : 'var(--text-faint)' }}>
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
        <table className="ledger" style={{ whiteSpace: 'nowrap' }}>
          <thead><tr>
            {([['', ''], ['S₀', 'calib_tip_s0'], ['μ p.a.', 'calib_tip_mu'], ['V₀ (σ)', 'calib_tip_v0'], ['θ (σ)', 'calib_tip_theta'], ['κ', 'calib_tip_kappa'], ['ξ', 'calib_tip_xi'], ['ρ', 'calib_tip_rho'], ['Feller', 'calib_tip_feller']] as const).map(([h, tip], i) => (
              <th key={i} className={i === 0 ? undefined : 'num'} title={tip ? t(tip) : undefined} style={{ cursor: tip ? 'help' : undefined }}>
                {h}{tip ? <span style={{ color: 'var(--text-faint)', marginLeft: 3 }}>ⓘ</span> : ''}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {summary.calibration.map((c) => {
              const ok = (c.feller ?? 0) >= 0
              return (
                <tr key={c.name}>
                  <td>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                      <TickerLogo symbol={nameToSym[c.name] ?? c.name} name={c.name} size={16} />{c.name}
                    </span>
                  </td>
                  <td className="num">{num(c.S0, 2)}</td>
                  <td className="num" style={{ color: (c.mu ?? 0) >= 0 ? 'var(--text)' : 'var(--red)' }}>{pct(c.mu, 1)}</td>
                  <td className="num">{sig(c.V0)}</td>
                  <td className="num">{sig(c.theta)}</td>
                  <td className="num">{num(c.kappa, 2)}</td>
                  <td className="num">{num(c.xi, 2)}</td>
                  <td className="num">{num(c.rho, 3)}</td>
                  <td className="num">
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
