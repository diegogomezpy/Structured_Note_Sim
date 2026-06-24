import { useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Icon from './Icon'
import type { NoteTerms, ReportSection } from '../api/types'
import type { RunOpts } from './SetupRail'

type Status = 'idle' | 'running' | 'done' | 'error'

const SECTIONS: { id: ReportSection; label: string; desc: string }[] = [
  { id: 'mc', label: 'sec_mc', desc: 'sec_mc_desc' },
  { id: 'calibration', label: 'sec_calib', desc: 'sec_calib_desc' },
  { id: 'backtest', label: 'sec_bt', desc: 'sec_bt_desc' },
  { id: 'live', label: 'sec_live', desc: 'sec_live_desc' },
]

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get('Content-Disposition') || ''
  const m = cd.match(/filename="?([^"]+)"?/)
  return m ? m[1] : fallback
}

export default function ReportPanel({ terms, opts }: { terms: NoteTerms; opts: RunOpts }) {
  const { t, lang } = useI18n()
  const hasLive = !!terms.issue_date
  const [selected, setSelected] = useState<Set<ReportSection>>(
    () => new Set<ReportSection>(['mc', 'calibration', 'backtest', ...(hasLive ? ['live' as const] : [])]),
  )
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')

  const toggle = (id: ReportSection) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
    setStatus('idle')
  }

  const generate = async () => {
    setStatus('running')
    setError('')
    try {
      const res = await api.report({
        terms, sections: [...selected], lang,
        n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine,
      })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filenameFrom(res, 'structured_note_report.pdf')
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      setStatus('done')
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
      setStatus('error')
    }
  }

  const none = selected.size === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('report_intro')}</div>

      <Panel title={t('report_sections')}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          {SECTIONS.map((s) => {
            const disabled = s.id === 'live' && !hasLive
            const on = selected.has(s.id) && !disabled
            return (
              <button key={s.id} onClick={() => !disabled && toggle(s.id)} disabled={disabled}
                style={{
                  textAlign: 'left', cursor: disabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                  padding: '13px 15px', borderRadius: 12, opacity: disabled ? 0.5 : 1,
                  border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`,
                  background: on ? 'var(--accent-weak)' : 'var(--surface)',
                  transition: 'border-color .12s ease, background .12s ease',
                }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                  <span style={{
                    width: 18, height: 18, borderRadius: 6, flexShrink: 0,
                    border: `1.5px solid ${on ? 'var(--accent)' : 'var(--border-strong, var(--text-faint))'}`,
                    background: on ? 'var(--accent)' : 'transparent',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
                  }}>{on && <Icon name="check" size={12} />}</span>
                  <span style={{ fontSize: 13.5, fontWeight: 600 }}>{t(s.label)}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, paddingLeft: 28 }}>
                  {disabled ? t('report_live_na') : t(s.desc)}
                </div>
              </button>
            )
          })}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 14, lineHeight: 1.5 }}>{t('report_note')}</div>
      </Panel>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <button className="btn btn--primary" onClick={generate}
                disabled={status === 'running' || none}
                style={{ padding: '12px 22px', fontSize: 14 }}>
          <Icon name={status === 'running' ? 'spinner' : 'chart'} size={16} />
          {status === 'running' ? t('report_generating') : t('report_generate')}
        </button>
        {none && <span style={{ fontSize: 12.5, color: 'var(--amber)' }}>{t('report_select_one')}</span>}
        {status === 'done' && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--green)' }}>
            <Icon name="check" size={15} /> {t('report_downloaded')}
          </span>
        )}
        {status === 'error' && (
          <span style={{ fontSize: 12.5, color: 'var(--red)' }}><strong>{t('error')}.</strong> {error}</span>
        )}
      </div>
    </div>
  )
}
