import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import TickerLogo from './TickerLogo'
import Icon from './Icon'
import { Select } from './fields'
import type { UnderlyingOption } from '../api/types'

const MAX = 5

function nameFromLabel(label: string): string {
  return label.includes(' — ') ? label.split(' — ')[1] : label
}

export default function UnderlyingPicker({
  tickers, onChange,
}: { tickers: Record<string, string>; onChange: (t: Record<string, string>) => void }) {
  const { t } = useI18n()
  const [universe, setUniverse] = useState<UnderlyingOption[]>([])
  const [showCustom, setShowCustom] = useState(false)
  const [sym, setSym] = useState('')
  const [nm, setNm] = useState('')

  useEffect(() => { api.underlyings().then(setUniverse).catch(() => {}) }, [])

  const entries = Object.entries(tickers)
  const atMax = entries.length >= MAX
  const selected = new Set(Object.keys(tickers))
  const available = universe.filter((o) => !selected.has(o.symbol))

  const add = (symbol: string, name: string) => {
    if (atMax || !symbol || tickers[symbol]) return
    onChange({ ...tickers, [symbol]: name })
  }
  const remove = (s: string) => {
    if (entries.length <= 1) return
    const c = { ...tickers }; delete c[s]; onChange(c)
  }
  const addCustom = () => {
    const s = sym.trim().toUpperCase()
    if (!s) return
    add(s, nm.trim() || s)
    setSym(''); setNm('')
  }

  return (
    <div>
      <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 8 }}>{t('underlyings')}</label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 10 }}>
        {entries.map(([s, name]) => (
          <span key={s} className="pill"
                style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)', paddingLeft: 5, paddingRight: 6 }}>
            <TickerLogo symbol={s} name={name} size={17} />{name}
            {entries.length > 1 && (
              <button onClick={() => remove(s)} aria-label={`Remove ${name}`} className="icon-remove"
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', display: 'inline-flex', padding: 0, marginLeft: 1 }}>
                <Icon name="x" size={13} />
              </button>
            )}
          </span>
        ))}
      </div>

      {!atMax ? (
        <div style={{ marginBottom: 8 }}>
          <Select value="" placeholder={`＋ ${t('add_underlying')}`} ariaLabel={t('add_underlying')}
                  options={available.map((o) => ({ value: o.symbol, label: o.label }))}
                  onChange={(sym) => { const o = universe.find((u) => u.symbol === sym); if (o) add(o.symbol, nameFromLabel(o.label)) }} />
        </div>
      ) : (
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 8 }}>{t('max_underlyings')}</div>
      )}

      {!atMax && (
        <div>
          <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => setShowCustom((v) => !v)}>
            <Icon name="plus" size={13} /> {t('add_custom')}
          </button>
          {showCustom && (
            <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
              <input placeholder={t('ul_symbol')} value={sym} onChange={(e) => setSym(e.target.value)} style={{ flex: '0 0 88px', textTransform: 'uppercase' }} />
              <input placeholder={t('ul_name')} value={nm} onChange={(e) => setNm(e.target.value)} style={{ flex: 1 }} />
              <button className="btn" style={{ padding: '0 12px' }} onClick={addCustom}>{t('add_btn')}</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
