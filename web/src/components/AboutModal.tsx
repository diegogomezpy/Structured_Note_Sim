import Modal from './Modal'
import { useI18n } from '../i18n/I18nProvider'

/** "About the author" dialog — a short bio and contact links, opened from the
    header. Author/contact details live here as constants (proper nouns / URLs);
    only the prose lives in i18n. Set `linkedin` to your profile URL to show the
    LinkedIn link (it's hidden until then). */
const AUTHOR = {
  name: 'Diego Gomez',
  email: 'diegogomezzx@gmail.com',
  github: 'https://github.com/diegogomezpy',
  linkedin: 'https://www.linkedin.com/in/diegogomezpy/',
}

export default function AboutModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const links: Array<{ label: string; href: string; ext: boolean }> = [
    { label: t('about_email'), href: `mailto:${AUTHOR.email}`, ext: false },
    { label: t('about_github'), href: AUTHOR.github, ext: true },
  ]
  if (AUTHOR.linkedin) links.push({ label: t('about_linkedin'), href: AUTHOR.linkedin, ext: true })

  return (
    <Modal title={t('about_title')} onClose={onClose} width={520}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em' }}>
            {AUTHOR.name}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>{t('about_role')}</div>
        </div>
        <p style={{ fontSize: 13.5, lineHeight: 1.65, color: 'var(--text-muted)', margin: 0 }}>{t('about_bio')}</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 2 }}>
          {links.map(({ label, href, ext }) => (
            <a key={label} href={href}
               target={ext ? '_blank' : undefined} rel={ext ? 'noreferrer' : undefined}
               className="btn btn--ghost"
               style={{ padding: '7px 13px', fontSize: 12.5, textDecoration: 'none' }}>
              {label}
            </a>
          ))}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.5, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
          {t('about_license')}
        </div>
      </div>
    </Modal>
  )
}
