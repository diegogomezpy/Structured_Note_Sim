import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import TickerLogo from './TickerLogo'
import BarrierMonitor from './BarrierMonitor'
import AnimatedNumber from './AnimatedNumber'
import { InfoDot } from './Tooltip'
import { pct, pctSigned, num } from '../lib/format'
import { monthsNum } from '../lib/terms'
import type { LiveObsRow, LiveResult, LiveStatus, NoteTerms } from '../api/types'

const STATUS_META: Record<LiveStatus, { key: string; color: string }> = {
  autocalled:    { key: 'live_st_autocalled',    color: 'var(--accent)' },
  coupon_paid:   { key: 'live_st_coupon_paid',   color: 'var(--green)' },
  coupon_missed: { key: 'live_st_coupon_missed', color: 'var(--red)' },
  no_coupon:     { key: 'live_st_no_coupon',     color: 'var(--amber)' },
  upcoming:      { key: 'live_st_upcoming',      color: 'var(--text-faint)' },
  // participation cliquet reset statuses
  part_gain:     { key: 'live_st_lock_gain',     color: 'var(--green)' },
  part_loss:     { key: 'live_st_lock_loss',     color: 'var(--red)' },
  part_flat:     { key: 'live_st_flat',          color: 'var(--text-faint)' },
  running:       { key: 'live_st_running',       color: 'var(--accent)' },
}

/** Stat card with an optional signed-delta subline (and tone). Pass a fraction
    `num` (+`dp`, `signed`) to count it up from 0 with a split % unit; else a
    plain `value` string (e.g. the worst-asset name). */
function Stat({ label, value, num: figure, dp = 1, signed, sub, subTone, help, children }: {
  label: string; value?: string; num?: number | null | undefined; dp?: number; signed?: boolean
  sub?: string; subTone?: string; help?: string; children?: React.ReactNode
}) {
  const animate = figure != null && Number.isFinite(figure)
  const fmt = signed ? (n: number) => `${n >= 0 ? '+' : ''}${num(n, dp)}` : (n: number) => num(n, dp)
  return (
    <div className="card lift" style={{ padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>
        {label}{help && <InfoDot title={label} body={help} />}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {children}
        <div className="mono" style={{ fontSize: 24, fontWeight: 600, lineHeight: 1, display: 'flex', alignItems: 'baseline', gap: 1 }}>
          {animate
            ? <><AnimatedNumber value={figure! * 100} format={fmt} animateOnMount /><i className="fig-unit" style={{ color: 'inherit', opacity: 0.7 }}>%</i></>
            : value}
        </div>
      </div>
      {sub && <div className="mono" style={{ fontSize: 12, marginTop: 7, color: subTone ?? 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

/** The position band — only for a note bought on the secondary market. What was
    paid and when, then the three numbers that follow from it: income received
    since settlement, the discount/premium still pulling to the redemption level,
    and the total return on cost if the position closed there today. */
function PositionBand({ s }: { s: NonNullable<LiveResult['summary']> }) {
  const { t } = useI18n()
  if (!s.secondary) return null
  const tone = (d: number | null | undefined) => (d == null ? 'var(--text)' : d >= 0 ? 'var(--green)' : 'var(--red)')
  return (
    <Panel title={t('live_position')} pad={16}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: '4px 18px' }}>
        <span>{t('settlement_date')} <span className="mono" style={{ color: 'var(--text)' }}>{s.settlement_date}</span></span>
        <span>{t('purchase_price')} <span className="mono" style={{ color: 'var(--text)' }}>{pct(s.purchase_price, 3)}</span></span>
        {!!s.accrued_at_purchase && (
          <span>{t('accrued_at_purchase')} <span className="mono" style={{ color: 'var(--text)' }}>{pct(s.accrued_at_purchase, 3)}</span></span>
        )}
        <span>{t('cost_basis')} <span className="mono" style={{ color: 'var(--text)' }}>{pct(s.cost_basis, 3)}</span></span>
        <span>{t('live_held')} <span className="mono" style={{ color: 'var(--text)' }}>{num(monthsNum(s.holding_years ?? 0), 1)} {t('live_mo')}</span></span>
      </div>
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
        {/* Coupon income since settlement — only on a note that pays coupons.
            A participation note has none, so this tile showed a structural
            0.00%, which reads as a measurement rather than as "not applicable". */}
        {s.note_type !== 'participation' && (
          <Stat label={t('live_income_since')} num={s.income_since} dp={2} help={t('live_tip_income_since')} />
        )}
        <Stat label={t('live_pull_to_par')} num={s.pull_to_par} dp={2} signed subTone={tone(s.pull_to_par)} help={t('live_tip_pull_to_par')} />
        <Stat label={t('live_return_on_cost')} num={s.return_on_cost} dp={2} signed subTone={tone(s.return_on_cost)} help={t('live_tip_return_on_cost')} />
      </div>
    </Panel>
  )
}

/** Lifecycle timeline + optional gap warning — shared by the autocall and
    participation live views. */
function Lifecycle({ s }: { s: NonNullable<LiveResult['summary']> }) {
  const { t } = useI18n()
  return (<>
    <Panel pad={18}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)', marginBottom: 9 }}>
        <span>{t('live_issued')} <span className="mono" style={{ color: 'var(--text)' }}>{s.issue_date}</span></span>
        <span className="mono" style={{ color: 'var(--text)' }}>{num(monthsNum(s.elapsed_years ?? 0), 1)} {t('live_mo')} {t('live_elapsed')} · {num(monthsNum(s.remaining_years ?? 0), 1)} {t('live_mo')} {t('live_remaining')}</span>
        <span>{t('live_matures')} <span className="mono" style={{ color: 'var(--text)' }}>{s.maturity_date}</span></span>
      </div>
      <div style={{ height: 8, borderRadius: 5, background: 'var(--surface-2)', overflow: 'hidden' }}>
        <div className="grow-x" style={{ width: `${Math.round((s.pct_elapsed ?? 0) * 100)}%`, height: '100%', background: 'var(--accent)', borderRadius: 5, transition: 'width .5s ease' }} />
      </div>
    </Panel>
    {(s.history_gap_days ?? 0) > 7 && (
      <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: 'var(--amber-weak)', border: '1px solid var(--amber)', borderRadius: 11, fontSize: 12.5 }}>
        <Icon name="info" size={15} /> {t('live_gap_warn')}
      </div>
    )}
  </>)
}

/** Participation current-performance: the note against its own maturity payoff —
    basket today → redemption if it settled now, distance to breakeven / floor /
    cap. Cliquet notes also show the locked-in per-reset accrual. */
function ParticipationLive({ result }: { result: LiveResult }) {
  const { t } = useI18n()
  const s = result.summary!
  const assets = result.assets ?? []
  const rows = result.obs_rows ?? []
  const periodic = !!s.participation_periodic
  const tone = (d: number | null | undefined) => (d == null ? 'var(--text)' : d >= 0 ? 'var(--green)' : 'var(--red)')
  const basketDelta = s.basket_today != null ? s.basket_today - 1 : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('live_intro_part')}</div>
      <Lifecycle s={s} />
      <PositionBand s={s} />

      {/* Headline: basket today + projected redemption */}
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
        <Stat label={t('live_basket_today')} num={s.basket_today} dp={1}
              sub={`${pctSigned(basketDelta, 1)} ${t('live_vs_par')}`} subTone={tone(basketDelta)} help={t('live_tip_basket', { b: t(`basket_${s.participation_basket}`) })} />
        <Stat label={periodic ? t('live_proj_redemption_cliquet') : t('live_proj_redemption')} num={s.projected_redemption} dp={1}
              sub={`${pctSigned(s.projected_gain, 1)} ${t('live_vs_par')}`} subTone={tone(s.projected_gain)} help={t('live_tip_projection')} />
        <Stat label={t('live_worst_asset')} value={s.worst_asset}>
          <TickerLogo symbol={s.worst_symbol || s.worst_asset} name={s.worst_asset} size={22} />
        </Stat>
        {s.dist_breakeven != null && (
          <Stat label={t('live_dist_breakeven')} num={s.dist_breakeven} dp={1} signed subTone={tone(s.dist_breakeven)}
                sub={t('live_ref_level', { v: pct(s.breakeven_level, 0) })} help={t('live_tip_breakeven')} />
        )}
      </div>

      {/* Distances to floor / cap; cliquet accrual */}
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
        {s.dist_protection != null && (
          <Stat label={t('live_dist_protection')} num={s.dist_protection} dp={1} signed subTone={tone(s.dist_protection)}
                sub={t('live_ref_level', { v: pct(s.protection_level, 0) })} />
        )}
        {s.dist_cap != null && (
          <Stat label={t('live_dist_cap')} num={s.dist_cap} dp={1} signed
                sub={t('live_ref_level', { v: pct(s.cap_level, 0) })} />
        )}
        {periodic && (<>
          <Stat label={t('live_accrued_income')} num={s.accrued_income} dp={2} signed subTone={tone(s.accrued_income)} help={t('live_tip_accrued')} />
          <Stat label={t('live_resets_done')} value={`${s.n_reset_done ?? 0} / ${s.n_reset_total ?? 0}`}
                sub={s.current_income != null ? `${t('live_current_period')}: ${pctSigned(s.current_income, 2)}` : undefined}
                subTone={tone(s.current_income)} />
        </>)}
      </div>

      {/* Basket toward the protection floor */}
      {!periodic && s.basket_today != null && s.protection_level != null && (
        <BarrierMonitor now={s.basket_today} barrier={s.protection_level} />
      )}

      {/* Per-asset vs strike */}
      <Panel title={t('live_asset_perf')} pad={16}>
        <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
          {assets.map((a) => {
            const d = a.perf != null ? a.perf - 1 : null
            return (
              <div key={a.name} className="card lift" style={{ padding: '12px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <TickerLogo symbol={a.symbol || a.name} name={a.name} size={18} />
                  <span style={{ fontSize: 12.5, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                </div>
                <div className="mono" style={{ fontSize: 19, fontWeight: 600, display: 'flex', alignItems: 'baseline', gap: 1 }}>
                  {a.perf != null
                    ? <><AnimatedNumber value={a.perf * 100} format={(n) => num(n, 1)} animateOnMount /><i className="fig-unit" style={{ opacity: 0.7 }}>%</i></>
                    : '—'}
                </div>
                <div className="mono" style={{ fontSize: 11.5, marginTop: 4, color: tone(d) }}>{pctSigned(d, 1)} {t('live_vs_strike')}</div>
              </div>
            )
          })}
        </div>
      </Panel>

      {result.figure && (
        <Panel title={t('live_chart_title')} pad={14}>
          <div style={{ height: 440 }}><Figure fig={result.figure} name="live_performance" /></div>
        </Panel>
      )}

      {/* Reset history (cliquet only) */}
      {periodic && rows.length > 0 && (
        <Panel title={t('live_reset_history')} pad={0}>
          <div style={{ maxHeight: 420, overflow: 'auto' }}>
            <table className="ledger">
              <thead>
                <tr style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
                  {[t('live_col_period'), t('live_col_date'), t('live_col_status'), t('live_col_move'), t('live_col_income'), t('live_col_cumulative')].map((h, i) => (
                    <th key={h} className={i >= 3 ? 'num' : undefined}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r: LiveObsRow) => {
                  const m = STATUS_META[r.status]
                  return (
                    <tr key={r.period} style={{ opacity: r.upcoming || r.held === false ? 0.55 : 1 }}
                        title={r.held === false ? t('live_before_purchase') : undefined}>
                      <td style={{ fontWeight: 600 }}>{r.period}</td>
                      <td style={{ color: 'var(--text-muted)' }}>{r.date ?? '—'}</td>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ width: 8, height: 8, borderRadius: '50%', background: m.color }} />
                          {t(m.key)}
                        </span>
                      </td>
                      <td className="num" style={{ color: r.move != null ? tone(r.move) : 'var(--text-faint)' }}>{r.move != null ? pctSigned(r.move, 1) : '—'}</td>
                      <td className="num" style={{ color: r.income != null ? tone(r.income) : 'var(--text-faint)' }}>{r.income != null ? pctSigned(r.income, 2) : '—'}</td>
                      <td className="num">{r.cumulative != null ? pctSigned(r.cumulative, 2) : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  )
}

export default function LivePanel({ result }: { result: LiveResult; terms: NoteTerms }) {
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

  if (result.summary?.note_type === 'participation') return <ParticipationLive result={result} />

  const s = result.summary!
  const assets = result.assets ?? []
  const rows = result.obs_rows ?? []
  const elapsed = num(monthsNum(s.elapsed_years ?? 0), 1)
  const remaining = num(monthsNum(s.remaining_years ?? 0), 1)
  const wofDelta = s.wof_today != null ? s.wof_today - 1 : null
  const tone = (d: number | null | undefined) => (d == null ? 'var(--text)' : d >= 0 ? 'var(--green)' : 'var(--red)')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('live_intro')}</div>

      {/* Lifecycle timeline */}
      <Panel pad={18}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)', marginBottom: 9 }}>
          <span>{t('live_issued')} <span className="mono" style={{ color: 'var(--text)' }}>{s.issue_date}</span></span>
          <span className="mono" style={{ color: 'var(--text)' }}>{elapsed} {t('live_mo')} {t('live_elapsed')} · {remaining} {t('live_mo')} {t('live_remaining')}</span>
          <span>{t('live_matures')} <span className="mono" style={{ color: 'var(--text)' }}>{s.maturity_date}</span></span>
        </div>
        <div style={{ height: 8, borderRadius: 5, background: 'var(--surface-2)', overflow: 'hidden' }}>
          <div className="grow-x" style={{ width: `${Math.round((s.pct_elapsed ?? 0) * 100)}%`, height: '100%', background: 'var(--accent)', borderRadius: 5, transition: 'width .5s ease' }} />
        </div>
      </Panel>

      {s.history_gap_days > 7 && (
        <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: 'var(--amber-weak)', border: '1px solid var(--amber)', borderRadius: 11, fontSize: 12.5 }}>
          <Icon name="info" size={15} /> {t('live_gap_warn')}
        </div>
      )}

      {!s.alive && (
        <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', background: 'var(--accent-weak)', border: '1px solid var(--accent)', borderRadius: 11, fontSize: 13, color: 'var(--text)' }}>
          <Icon name="check" size={16} /> {t('live_called_banner', { n: s.autocall_period ?? 0 })}
        </div>
      )}

      {/* Today + barriers */}
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
        <Stat label={t('live_wof_today')} num={s.wof_today} dp={1}
              sub={`${pctSigned(wofDelta, 1)} ${t('live_vs_strike')}`} subTone={tone(wofDelta)} />
        <Stat label={t('live_worst_asset')} value={s.worst_asset}>
          <TickerLogo symbol={s.worst_symbol || s.worst_asset} name={s.worst_asset} size={22} />
        </Stat>
        <Stat label={t('live_ki_buffer')} num={s.ki_buffer} dp={1} signed subTone={tone(s.ki_buffer)}
              sub={t('live_ref_barrier', { v: pct(s.knock_in_barrier, 0) })} />
        <Stat label={t('live_ac_buffer')} num={s.ac_buffer} dp={1} signed subTone={tone(s.ac_buffer)}
              sub={t('live_ref_autocall', { v: pct(s.next_ac_barrier, 0) })} />
      </div>

      {/* Barrier monitor — worst-of toward the knock-in */}
      {s.wof_today != null && s.knock_in_barrier != null && (
        <BarrierMonitor now={s.wof_today} barrier={s.knock_in_barrier} />
      )}

      {/* Per-asset vs strike */}
      <Panel title={t('live_asset_perf')} pad={16}>
        <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
          {assets.map((a) => {
            const d = a.perf != null ? a.perf - 1 : null
            return (
              <div key={a.name} className="card lift" style={{ padding: '12px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <TickerLogo symbol={a.symbol || a.name} name={a.name} size={18} />
                  <span style={{ fontSize: 12.5, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                </div>
                <div className="mono" style={{ fontSize: 19, fontWeight: 600, display: 'flex', alignItems: 'baseline', gap: 1 }}>
                  {a.perf != null
                    ? <><AnimatedNumber value={a.perf * 100} format={(n) => num(n, 1)} animateOnMount /><i className="fig-unit" style={{ opacity: 0.7 }}>%</i></>
                    : '—'}
                </div>
                <div className="mono" style={{ fontSize: 11.5, marginTop: 4, color: tone(d) }}>{pctSigned(d, 1)} {t('live_vs_strike')}</div>
              </div>
            )
          })}
        </div>
      </Panel>

      {/* Coupon KPIs. "Coupons paid" is what the NOTE has paid since issue; a
          secondary holder's own income (and the IRR built on it) lives in the
          position band below. */}
      <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
        <Stat label={t('live_coupons_paid')} num={s.total_coupons} dp={2} />
        <Stat label={t('live_irr_to_date')} num={s.irr_to_date} dp={2} subTone={tone(s.irr_to_date)}
              sub={s.secondary ? t('live_since_settlement') : undefined} />
      </div>

      <PositionBand s={s} />

      {(s.pending_coupons ?? 0) > 0 && (
        <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>
          {t('live_pending', { n: s.pending_coupons ?? 0, v: pct(s.pending_value, 2) })}
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
          <table className="ledger">
            <thead>
              <tr style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
                {[t('live_col_period'), t('live_col_date'), t('live_col_status'), t('live_col_wof'), t('live_col_coupon'), t('live_col_cumulative')].map((h, i) => (
                  <th key={h} className={i >= 3 ? 'num' : undefined}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r: LiveObsRow) => {
                const m = STATUS_META[r.status]
                // Periods fixed before settlement paid someone else — dimmed, and
                // their coupon loses the "received" green.
                const preOwned = r.held === false
                return (
                  <tr key={r.period} style={{ opacity: r.upcoming || preOwned ? 0.55 : 1 }}
                      title={preOwned ? t('live_before_purchase') : undefined}>
                    <td style={{ fontWeight: 600 }}>{r.period}</td>
                    <td style={{ color: 'var(--text-muted)' }}>{r.date ?? '—'}</td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: m.color }} />
                        {t(m.key)}
                      </span>
                    </td>
                    <td className="num" style={{ color: r.wof != null && r.wof < (s.knock_in_barrier ?? 0) ? 'var(--red)' : 'var(--text)' }}>{r.wof != null ? pct(r.wof, 1) : '—'}</td>
                    <td className="num" style={{ color: r.coupon && !preOwned ? 'var(--green)' : 'var(--text-faint)' }}>{r.coupon ? pct(r.coupon, 2) : '—'}</td>
                    <td className="num">{r.cumulative != null ? pct(r.cumulative, 2) : '—'}</td>
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
