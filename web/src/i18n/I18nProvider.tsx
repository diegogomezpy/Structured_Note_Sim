import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { makeT, type Lang } from './strings'

interface I18nCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: string, vars?: Record<string, string | number>) => string
}

const Ctx = createContext<I18nCtx>({ lang: 'en', setLang: () => {}, t: (k) => k })

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const saved = localStorage.getItem('sns-lang')
    return saved === 'es' ? 'es' : 'en'
  })
  useEffect(() => { localStorage.setItem('sns-lang', lang) }, [lang])
  return <Ctx.Provider value={{ lang, setLang, t: makeT(lang) }}>{children}</Ctx.Provider>
}

export const useI18n = () => useContext(Ctx)
