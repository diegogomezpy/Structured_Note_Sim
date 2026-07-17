import { useI18n } from '../i18n/I18nProvider'
import TickerLogo from './TickerLogo'
import { InfoDot } from './Tooltip'
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
                <td className="num" style={{ color: 'var(--text-muted)' }}>{num(summary.obs_times[i] * 12, 1)}</td>
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

/** A calibration column header — symbol + info dot, one per category. Greek
    symbols render verbatim (the .ledger header's uppercase would mangle μ/κ/ξ/ρ). */
function ColHead({ sym, tip }: { sym: string; tip: string }) {
  const { t } = useI18n()
  return (
    <th className="num" style={{ textTransform: 'none', whiteSpace: 'nowrap' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'flex-end' }}>{sym}<InfoDot title={sym} body={t(tip)} /></span>
    </th>
  )
}

export function CalibrationTable({ summary, nameToSym }: { summary: SimSummary; nameToSym: Record<string, string> }) {
  const { t } = useI18n()
  const sig = (v: number | null) => (v == null ? '—' : `${num(Math.sqrt(Math.abs(v)) * 100, 0)}%`)

  return (
    <div>
      {/* One consolidated table: a single header row of categories (each with an
          info dot), one row per underlying. The first column absorbs the slack
          (width:100%) so the numeric columns stay tight and aligned rather than
          sprawling across the panel. */}
      <div style={{ overflowX: 'auto' }}>
        <table className="ledger" style={{ whiteSpace: 'nowrap' }}>
          <thead>
            <tr>
              <th style={{ width: '100%', textTransform: 'none' }}>{t('calib_underlying')}</th>
              <ColHead sym="S₀" tip="calib_tip_s0" />
              <ColHead sym="μ p.a." tip="calib_tip_mu" />
              <ColHead sym="V₀ (σ)" tip="calib_tip_v0" />
              <ColHead sym="θ (σ)" tip="calib_tip_theta" />
              <ColHead sym="κ" tip="calib_tip_kappa" />
              <ColHead sym="ξ" tip="calib_tip_xi" />
              <ColHead sym="ρ" tip="calib_tip_rho" />
              <th className="num" style={{ textTransform: 'none' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'flex-end' }}>Feller<InfoDot title="Feller" body={t('calib_tip_feller')} /></span>
              </th>
            </tr>
          </thead>
          <tbody>
            {summary.calibration.map((c) => {
              const ok = (c.feller ?? 0) >= 0
              return (
                <tr key={c.name}>
                  <td>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <TickerLogo symbol={nameToSym[c.name] ?? c.name} name={c.name} size={18} />{c.name}
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

      {summary.t_dof != null && (
        <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 14 }}>
          {t('t_copula_dof')} {num(summary.t_dof, 1)}
        </div>
      )}
    </div>
  )
}
