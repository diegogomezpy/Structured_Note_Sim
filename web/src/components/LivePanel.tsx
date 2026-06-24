import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import TickerLogo from './TickerLogo'
import { pct, pctSigned, num } from '../lib/format'
import type { LiveObsRow, LiveResult, LiveStatus, NoteTerms } from '../api/types'

const STATUS_META: Record<LiveStatus, { key: string; color: string }> = {
  autocalled:    { key: 'live_st_autocalled',    color: 'var(--accent)' },
  coupon_paid:   { key: 'live_st_coupon_paid',   color: 'var(--green)' },
  coupon_missed: { key: 'live_st_coupon_missed', color: 'var(--red)' },
  no_coupon:     { key: 'live_st_no_coupon',     color: 'var(--amber)' },
  upcoming:      { key: 'live_st_upcoming',      color: 'var(--text-faint)' },
}

/** Stat card with an optional signed-delta subline (and tone). */
function Stat({ label, value, sub, subTone, help, children }: {
  label: string; value: string; sub?: string; subTone?: string; help?: string; children?: React.ReactNode
}) {
  return (
    <div className="card" style={{ padding: '14px 16px' }} title={help}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {children}
        <div className="mono" style={{ fontSize: 24, fontWeight: 600, lineHeight: 1 }}>{value}</div>
      </div>
      {sub && <div className="mono" style={{ fontSize: 12, marginTop: 7, color: subTone ?? 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

export default function LivePanel({ result, terms }: { result: LiveResult; terms: NoteTerms }) {
  const { t } = useI18n()

  if (!result.available) {
    const msg = result.reason === 'not_issued' ? t('live_not_issued')
      : result.reason === 'not_enough_data' ? t('live_no_data')
      : t('live_no_issue')
    return (
      <Panel pad={40}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 14, maxWidth: 520, margin: '0 auto', textAlign: 'center' }}>
          <Icon name="info" size={18} /> {msg}
        </div>
      </Panel>
    )
  }

  const s = result.summary!
  const assets = result.assets ?? []
  const rows = result.obs_rows ?? []
  const elapsed = num(s.elapsed_years, 2)
  const remaining = num(s.remaining_years, 2)
  const wofDelta = s.wof_today != null ? s.wof_today - 1 : null
  const tone = (d: number | null) => (d == null ? 'var(--text)' : d >= 0 ? 'var(--green)' : 'var(--red)')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('live_intro')}</div>

      {/* Lifecycle timeline */}
      <Panel pad={18}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)', marginBottom: 9 }}>
          <span>{t('live_issued')} <span className="mono" style={{ color: 'var(--text)' }}>{s.issue_date}</span></span>
          <span className="mono" style={{ color: 'var(--text)' }}>{elapsed} {t('live_y')} {t('live_elapsed')} · {remaining} {t('live_y')} {t('live_remaining')}</span>
          <span>{t('live_matures')} <span className="mono" style={{ color: 'var(--text)' }}>{s.maturity_date}</span></span>
        </div>
        <div style={{ height: 8, borderRadius: 5, background: 'var(--surface-2)', overflow: 'hidden' }}>
          <div style={{ width: `${Math.round((s.pct_elapsed ?? 0) * 100)}%`, height: '100%', background: 'var(--accent)', borderRadius: 5, transition: 'width .5s ease' }} />
        </div>
      </Panel>

      {s.history_gap_days > 7 && (
        <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: 'var(--amber-weak)', border: '1px solid var(--amber)', borderRadius: 11, fontSize: 12.5 }}>
          <Icon name="info" size={15} /> {t('live_gap_warn')}
        </div>
      )}

      {!s.alive && (
        <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', background: 'var(--accent-weak)', border: '1px solid var(--accent)', borderRadius: 11, fontSize: 13, color: 'var(--text)' }}>
          <Icon name="check" size={16} /> {t('live_called_banner', { n: s.autocall_period })}
        </div>
      )}

      {/* Today + barriers */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
        <Stat label={t('live_wof_today')} value={pct(s.wof_today, 1)}
              sub={`${pctSigned(wofDelta, 1)} ${t('live_vs_strike')}`} subTone={tone(wofDelta)} />
        <Stat label={t('live_worst_asset')} value={s.worst_asset}>
          <TickerLogo symbol={s.worst_symbol || s.worst_asset} name={s.worst_asset} size={22} />
        </Stat>
        <Stat label={t('live_ki_buffer')} value={pctSigned(s.ki_buffer, 1)} subTone={tone(s.ki_buffer)}
              sub={t('live_ref_barrier', { v: pct(s.knock_in_barrier, 0) })} />
        <Stat label={t('live_ac_buffer')} value={pctSigned(s.ac_buffer, 1)} subTone={tone(s.ac_buffer)}
              sub={t('live_ref_autocall', { v: pct(s.next_ac_barrier, 0) })} />
      </div>

      {/* Per-asset vs strike */}
      <Panel title={t('live_asset_perf')} pad={16}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
          {assets.map((a) => {
            const d = a.perf != null ? a.perf - 1 : null
            return (
              <div key={a.name} className="card" style={{ padding: '12px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <TickerLogo symbol={a.symbol || a.name} name={a.name} size={18} />
                  <span style={{ fontSize: 12.5, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                </div>
                <div className="mono" style={{ fontSize: 19, fontWeight: 600 }}>{pct(a.perf, 1)}</div>
                <div className="mono" style={{ fontSize: 11.5, marginTop: 4, color: tone(d) }}>{pctSigned(d, 1)} {t('live_vs_strike')}</div>
              </div>
            )
          })}
        </div>
      </Panel>

      {/* Coupon KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
        <Stat label={t('live_coupons_paid')} value={pct(s.total_coupons, 2)} />
        <Stat label={t('live_irr_to_date')} value={pct(s.irr_to_date, 2)}
              subTone={tone(s.irr_to_date)} />
      </div>

      {s.pending_coupons > 0 && (
        <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>
          {t('live_pending', { n: s.pending_coupons, v: pct(s.pending_value, 2) })}
        </div>
      )}
      {s.coupon_at_autocall_only && s.alive && (
        <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>
          {t('live_growth_premium', { v: pct(s.next_premium, 2) })}
        </div>
      )}

      {/* Live performance chart — above the table, so the visual reads first. */}
      {result.figure && (
        <Panel title={t('live_chart_title')} pad={14}>
          <div style={{ height: 440 }}><Figure fig={result.figure} name="live_performance" /></div>
        </Panel>
      )}

      {/* Observation history */}
      <Panel title={t('live_obs_history')} pad={0}>
        <div style={{ maxHeight: 420, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
                {[t('live_col_period'), t('live_col_date'), t('live_col_status'), t('live_col_wof'), t('live_col_coupon'), t('live_col_cumulative')].map((h, i) => (
                  <th key={h} style={{ textAlign: i >= 3 ? 'right' : 'left', padding: '10px 16px', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r: LiveObsRow) => {
                const m = STATUS_META[r.status]
                return (
                  <tr key={r.period} style={{ borderBottom: '1px solid var(--border)', opacity: r.upcoming ? 0.55 : 1 }}>
                    <td className="mono" style={{ padding: '9px 16px', fontWeight: 600 }}>{r.period}</td>
                    <td className="mono" style={{ padding: '9px 16px', color: 'var(--text-muted)' }}>{r.date ?? '—'}</td>
                    <td style={{ padding: '9px 16px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: m.color }} />
                        {t(m.key)}
                      </span>
                    </td>
                    <td className="mono" style={{ padding: '9px 16px', textAlign: 'right', color: r.wof != null && r.wof < (s.knock_in_barrier ?? 0) ? 'var(--red)' : 'var(--text)' }}>{r.wof != null ? pct(r.wof, 1) : '—'}</td>
                    <td className="mono" style={{ padding: '9px 16px', textAlign: 'right', color: r.coupon ? 'var(--green)' : 'var(--text-faint)' }}>{r.coupon ? pct(r.coupon, 2) : '—'}</td>
                    <td className="mono" style={{ padding: '9px 16px', textAlign: 'right' }}>{r.cumulative != null ? pct(r.cumulative, 2) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
