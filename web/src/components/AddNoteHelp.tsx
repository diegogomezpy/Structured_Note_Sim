import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Modal from './Modal'
import Icon from './Icon'

const TEMPLATE = {
  name: 'My Bank XS000000000 — 2Y Quarterly Autocall',
  issuer: 'My Bank',
  issuer_rating_sp: 'A+',
  issuer_rating_moody: 'A1',
  issuer_rating_fitch: 'A+',
  maturity: 2.0,
  payment_freq: 'quarterly',
  coupon_pa: 0.12,
  coupon_barrier: 0.70,
  autocall_barrier: 1.0,
  autocall_start_period: 1,
  knock_in_barrier: 0.60,
  principal_protection: 1.0,
  memory: true,
  coupon_basket: 'worst_of',
  autocall_basket: 'worst_of',
  one_star_level: null,
  call_steepness: null,
  autocall_step_down: 0.0,
  autocall_floor: null,
  coupon_at_autocall_only: false,
  capital_guarantee: null,
  upside_cap: null,
  tickers: { AAPL: 'Apple', MSFT: 'Microsoft' },
  issue_date: '2025-01-15',
  underlyings: { Apple: { analyst: { buy: 60, hold: 30, sell: 10 } } },
}
const TEMPLATE_JSON = JSON.stringify(TEMPLATE, null, 2)

// Exhaustive field reference (code keys are language-neutral; meanings are
// bilingual here to keep the global string table lean). `g` rows are section
// headers; everything below the first header is optional (sensible defaults).
type FieldRow = { g: string; es: string } | { k: string; en: string; es: string }
const FIELDS: FieldRow[] = [
  { g: 'Core terms', es: 'Términos principales' },
  { k: 'name', en: 'Name shown in the dropdown', es: 'Nombre en el menú' },
  { k: 'maturity', en: 'Tenor in years', es: 'Plazo en años' },
  { k: 'payment_freq', en: 'monthly · quarterly · semi-annual · annual', es: 'monthly · quarterly · semi-annual · annual' },
  { k: 'coupon_pa', en: 'Annual coupon (0.12 = 12%)', es: 'Cupón anual (0,12 = 12%)' },
  { k: 'coupon_barrier', en: 'Coupon barrier, fraction (0.70 = 70%)', es: 'Barrera de cupón, fracción (0,70 = 70%)' },
  { k: 'knock_in_barrier', en: 'Capital-protection barrier (0.60 = 60%)', es: 'Barrera de protección de capital (0,60 = 60%)' },
  { k: 'autocall_barrier', en: 'Autocall level (1.0 = 100%)', es: 'Nivel de autocall (1,0 = 100%)' },
  { k: 'autocall_start_period', en: 'First callable period (1-indexed)', es: 'Primer período rescatable (base 1)' },
  { k: 'memory', en: 'Memory coupons (true / false)', es: 'Cupones con memoria (true / false)' },
  { k: 'coupon_basket / autocall_basket', en: 'worst_of · best_of · average', es: 'worst_of · best_of · average' },
  { k: 'tickers', en: 'Yahoo symbol → display name', es: 'Símbolo Yahoo → nombre' },

  { g: 'Optional — structure', es: 'Opcional — estructura' },
  { k: 'principal_protection', en: 'Redemption floor when not knocked in (default 1.0)', es: 'Piso de redención sin knock-in (def. 1,0)' },
  { k: 'one_star_level', en: 'One-Star best-of overlay level, or null', es: 'Nivel One-Star (best-of), o null' },
  { k: 'call_steepness', en: 'null = hard autocall trigger (default)', es: 'null = disparo de autocall duro (def.)' },
  { k: 'autocall_step_down', en: 'Per-period drop of the autocall barrier (0 = constant)', es: 'Caída por período de la barrera de autocall (0 = constante)' },
  { k: 'autocall_floor', en: 'Min autocall barrier when stepping down, or null', es: 'Barrera mínima de autocall al decrecer, o null' },
  { k: 'coupon_at_autocall_only', en: 'true = premium paid only at call (no periodic coupon)', es: 'true = prima solo al rescate (sin cupón periódico)' },
  { k: 'capital_guarantee', en: 'Guaranteed min redemption (e.g. 0.95), or null', es: 'Redención mínima garantizada (ej. 0,95), o null' },
  { k: 'upside_cap', en: 'Max gain above par (0.15 = +15%), or null', es: 'Ganancia máxima sobre par (0,15 = +15%), o null' },
  { k: 'issue_date', en: 'YYYY-MM-DD — enables Current performance', es: 'AAAA-MM-DD — activa Rendimiento actual' },

  { g: 'Optional — secondary-market position', es: 'Opcional — posición en secundario' },
  { k: 'settlement_date', en: 'YYYY-MM-DD you bought it (default: held from issue)', es: 'AAAA-MM-DD de la compra (def.: desde la emisión)' },
  { k: 'purchase_price', en: 'Clean price paid, fraction of nominal (0.95 = 95%)', es: 'Precio limpio pagado, fracción del nominal (0,95 = 95%)' },
  { k: 'accrued_at_purchase', en: 'Accrued coupon settled on top (0 = clean trade)', es: 'Cupón corrido liquidado además (0 = operación limpia)' },

  { g: 'Optional — issuer', es: 'Opcional — emisor' },
  { k: 'issuer', en: 'Issuing bank (display + favicon)', es: 'Banco emisor (visual + favicon)' },
  { k: 'issuer_description', en: 'Prose blurb (auto-filled from Yahoo if omitted)', es: 'Descripción (se rellena desde Yahoo si se omite)' },
  { k: 'issuer_rating_sp / _moody / _fitch', en: 'Agency credit ratings (A+, A1, AA-)', es: 'Calificaciones de agencias (A+, A1, AA-)' },

  { g: 'Optional — per-underlying overrides', es: 'Opcional — ajustes por subyacente' },
  { k: 'underlyings', en: 'Keyed by display name: { description, logo, analyst {buy,hold,sell}, sector … }', es: 'Por nombre: { description, logo, analyst {buy,hold,sell}, sector … }' },
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
            {FIELDS.map((f, i) => (
              'g' in f ? (
                <div key={`g${i}`} style={{ gridColumn: '1 / -1', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)', marginTop: i ? 8 : 0 }}>
                  {lang === 'es' ? f.es : f.g}
                </div>
              ) : (
                <div key={f.k} style={{ display: 'contents' }}>
                  <code style={{ fontFamily: 'IBM Plex Mono, monospace', color: 'var(--accent-text)', whiteSpace: 'nowrap' }}>{f.k}</code>
                  <span style={{ color: 'var(--text-muted)' }}>{lang === 'es' ? f.es : f.en}</span>
                </div>
              )
            ))}
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-faint)', lineHeight: 1.55, background: 'var(--surface-2)', borderRadius: 9, padding: '10px 13px' }}>{t('addnote_tip')}</div>

          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>{t('addnote_auto_h')}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.6 }}>{t('addnote_auto')}</div>
          </div>
        </Modal>
      )}
    </>
  )
}
