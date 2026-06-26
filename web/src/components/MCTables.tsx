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

/** One Heston parameter, rendered as a register cell: a labelled head with an
    info dot, then the mono value. */
function ParamCell({ sym, tip, value, tone }: { sym: string; tip: string; value: string; tone?: string }) {
  const { t } = useI18n()
  return (
    <div style={{ background: 'var(--surface)', padding: '10px 13px' }}>
      {/* Symbols render verbatim (no uppercase — that mangles μ/κ/ξ/ρ). */}
      <div style={{ display: 'flex', alignItems: 'center', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 5 }}>
        <span className="mono">{sym}</span>
        <InfoDot title={sym} body={t(tip)} />
      </div>
      <div className="mono" style={{ fontSize: 18, fontWeight: 600, lineHeight: 1, color: tone ?? 'var(--text)' }}>{value}</div>
    </div>
  )
}

export function CalibrationTable({ summary, nameToSym }: { summary: SimSummary; nameToSym: Record<string, string> }) {
  const { t } = useI18n()
  const sig = (v: number | null) => (v == null ? '—' : `${num(Math.sqrt(Math.abs(v)) * 100, 0)}%`)

  return (
    <div>
      {/* One card per asset — a header (logo · name · Feller status) over a ruled
          grid of the Heston parameters. Reads cleanly for one underlying or many,
          where the old wide single-row table sprawled and looked disorganised. */}
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))', gap: 14 }}>
        {summary.calibration.map((c) => {
          const ok = (c.feller ?? 0) >= 0
          return (
            <div key={c.name} className="card lift" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '12px 15px' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <TickerLogo symbol={nameToSym[c.name] ?? c.name} name={c.name} size={20} />
                  <span style={{ fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                  <span className="pill" style={{ background: ok ? 'var(--green-weak)' : 'var(--amber-weak)', color: ok ? 'var(--green)' : 'var(--amber)' }}>
                    {ok ? t('feller_ok') : t('feller_warn')}
                  </span>
                  <InfoDot title="Feller" body={t('calib_tip_feller')} />
                </span>
              </div>
              {/* 1px gaps over a border-coloured ground draw hairlines between cells. */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(88px, 1fr))', gap: 1, background: 'var(--border)', borderTop: '1px solid var(--border)' }}>
                <ParamCell sym="S₀" tip="calib_tip_s0" value={num(c.S0, 2)} />
                <ParamCell sym="μ p.a." tip="calib_tip_mu" value={pct(c.mu, 1)} tone={(c.mu ?? 0) >= 0 ? undefined : 'var(--red)'} />
                <ParamCell sym="V₀ (σ)" tip="calib_tip_v0" value={sig(c.V0)} />
                <ParamCell sym="θ (σ)" tip="calib_tip_theta" value={sig(c.theta)} />
                <ParamCell sym="κ" tip="calib_tip_kappa" value={num(c.kappa, 2)} />
                <ParamCell sym="ξ" tip="calib_tip_xi" value={num(c.xi, 2)} />
                <ParamCell sym="ρ" tip="calib_tip_rho" value={num(c.rho, 3)} />
              </div>
            </div>
          )
        })}
      </div>

      {summary.t_dof != null && (
        <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 14 }}>
          {t('t_copula_dof')} {num(summary.t_dof, 1)}
        </div>
      )}
    </div>
  )
}
