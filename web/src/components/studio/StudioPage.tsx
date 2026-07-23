import { useI18n } from '../../i18n/I18nProvider'
import BrandMark from '../BrandMark'
import PdfDesigner from '../PdfDesigner'
import { useNavigate } from '../../lib/useHashRoute'
import type { BrandingStudio } from '../../lib/useBrandingStudio'
import type { NoteTerms } from '../../api/types'

/* The PDF Studio: a full-page surface at #/studio, deliberately outside the
   analytics shell.

   Report design is a different job from running a simulation — it wants width,
   a stable canvas and no note-setup rail competing for the screen — so the page
   drops the rail, the ticker tape and the note-structure panel and takes the
   whole viewport. It is its own scroll container: the columns inside scroll
   independently, and the page body never does.

   This slice keeps rendering the existing PdfDesigner so the move itself is
   verifiable in isolation; the three-column outline/proof/inspector layout
   replaces its body in a later slice. */
export default function StudioPage({ studio, terms }: {
  studio: BrandingStudio
  terms: NoteTerms | null
}) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const active = studio.brandLocalName || studio.brand.firm_name

  return (
    <div className="studio">
      <header className="studio__bar">
        <button className="btn btn--ghost" onClick={() => navigate('/')}
                style={{ padding: '6px 10px', flexShrink: 0 }}>
          <span aria-hidden style={{ fontSize: 14, lineHeight: 1 }}>←</span> {t('studio_back')}
        </button>
        <span className="studio__rule" aria-hidden />
        <BrandMark size={20} />
        <div style={{ minWidth: 0 }}>
          <div className="studio__title">{t('studio_title')}</div>
          {active && (
            <div className="studio__sub" title={active}>
              {t('rep_brand_active')} <strong>{active}</strong>
            </div>
          )}
        </div>
      </header>

      <div className="studio__body">
        {terms
          ? <PdfDesigner studio={studio} terms={terms} />
          : <div className="studio__empty">{t('studio_no_note')}</div>}
      </div>
    </div>
  )
}
