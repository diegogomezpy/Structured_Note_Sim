import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Modal from './Modal'
import Icon from './Icon'

const TEMPLATE = {
  name: 'My Bank XS000000000 — 2Y Quarterly Phoenix',
  issuer: 'My Bank',
  maturity: 2.0,
  payment_freq: 'quarterly',
  coupon_pa: 0.12,
  coupon_barrier: 0.70,
  autocall_barrier: 1.0,
  autocall_start_period: 1,
  knock_in_barrier: 0.60,
  memory: true,
  coupon_basket: 'worst_of',
  autocall_basket: 'worst_of',
  one_star_level: null,
  tickers: { AAPL: 'Apple', MSFT: 'Microsoft' },
  issue_date: '2025-01-15',
}
const TEMPLATE_JSON = JSON.stringify(TEMPLATE, null, 2)

// Field reference (code keys are language-neutral; meanings are bilingual here
// to keep the global string table lean).
const FIELDS: { k: string; en: string; es: string }[] = [
  { k: 'name', en: 'Name shown in the dropdown', es: 'Nombre en el menú' },
  { k: 'issuer', en: 'Issuing bank', es: 'Banco emisor' },
  { k: 'maturity', en: 'Tenor in years', es: 'Plazo en años' },
  { k: 'payment_freq', en: 'monthly · quarterly · semi-annual · annual', es: 'monthly · quarterly · semi-annual · annual' },
  { k: 'coupon_pa', en: 'Annual coupon (0.12 = 12%)', es: 'Cupón anual (0,12 = 12%)' },
  { k: 'coupon_barrier', en: 'Coupon barrier, fraction (0.70 = 70%)', es: 'Barrera de cupón, fracción (0,70 = 70%)' },
  { k: 'autocall_barrier', en: 'Autocall level (1.0 = 100%)', es: 'Nivel de autocall (1,0 = 100%)' },
  { k: 'autocall_start_period', en: 'First callable period', es: 'Primer período rescatable' },
  { k: 'knock_in_barrier', en: 'Capital-protection barrier', es: 'Barrera de protección de capital' },
  { k: 'memory', en: 'Memory coupons (true/false)', es: 'Cupones con memoria (true/false)' },
  { k: 'coupon_basket / autocall_basket', en: 'worst_of · best_of · average', es: 'worst_of · best_of · average' },
  { k: 'one_star_level', en: 'One-Star best-of level, or null', es: 'Nivel One-Star (best-of), o null' },
  { k: 'tickers', en: 'Yahoo symbol → display name', es: 'Símbolo Yahoo → nombre' },
  { k: 'issue_date', en: 'YYYY-MM-DD (optional, enables Current performance)', es: 'AAAA-MM-DD (opcional, activa Rendimiento actual)' },
]

export default function AddNoteHelp() {
  const { t, lang } = useI18n()
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const download = () => {
    const blob = new Blob([TEMPLATE_JSON], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'note_template.json'
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(TEMPLATE_JSON); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* ignore */ }
  }

  const Step = ({ n, children }: { n: number; children: React.ReactNode }) => (
    <li style={{ display: 'flex', gap: 11, alignItems: 'flex-start', marginBottom: 11 }}>
      <span style={{ flexShrink: 0, width: 22, height: 22, borderRadius: 999, background: 'var(--accent-weak)', color: 'var(--accent-text)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600 }}>{n}</span>
      <span style={{ fontSize: 13, lineHeight: 1.5, paddingTop: 1 }}>{children}</span>
    </li>
  )

  return (
    <>
      <button className="btn btn--ghost" style={{ padding: '3px 7px', fontSize: 11.5 }} onClick={() => setOpen(true)}>
        <Icon name="info" size={13} /> {t('addnote_trigger')}
      </button>

      {open && (
        <Modal title={t('addnote_title')} onClose={() => setOpen(false)} width={760}
          footer={<button className="btn" onClick={() => setOpen(false)}>{t('done')}</button>}>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 18 }}>{t('addnote_intro')}</div>

          <ol style={{ listStyle: 'none', padding: 0, margin: '0 0 18px' }}>
            <Step n={1}>{t('addnote_step1')}</Step>
            <Step n={2}>{t('addnote_step2')}</Step>
            <Step n={3}>{t('addnote_step3')}</Step>
          </ol>

          <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
            <button className="btn btn--primary" style={{ padding: '8px 14px' }} onClick={download}>
              <Icon name="chart" size={14} /> {t('addnote_download')}
            </button>
            <button className="btn" style={{ padding: '8px 14px' }} onClick={copy}>
              <Icon name={copied ? 'check' : 'plus'} size={14} /> {copied ? t('addnote_copied') : t('addnote_copy')}
            </button>
          </div>

          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>{t('addnote_example')}</div>
          <pre style={{
            background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10,
            padding: '14px 16px', fontSize: 12, lineHeight: 1.5, overflow: 'auto', margin: '0 0 20px',
            fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)', maxHeight: 260,
          }}>{TEMPLATE_JSON}</pre>

          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>{t('addnote_fields')}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', columnGap: 16, rowGap: 7, fontSize: 12.5, marginBottom: 18 }}>
            {FIELDS.map((f) => (
              <div key={f.k} style={{ display: 'contents' }}>
                <code style={{ fontFamily: 'IBM Plex Mono, monospace', color: 'var(--accent-text)', whiteSpace: 'nowrap' }}>{f.k}</code>
                <span style={{ color: 'var(--text-muted)' }}>{lang === 'es' ? f.es : f.en}</span>
              </div>
            ))}
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-faint)', lineHeight: 1.55, background: 'var(--surface-2)', borderRadius: 9, padding: '10px 13px' }}>{t('addnote_tip')}</div>
        </Modal>
      )}
    </>
  )
}
