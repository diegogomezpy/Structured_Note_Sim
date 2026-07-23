import { useCallback, useEffect, useState } from 'react'

/* Hash routing, deliberately hand-rolled.

   The app is a single living page driven by tab state, and pulling in a router
   to give one screen its own URL would be a lot of dependency for one route.
   The hash is enough: it survives a reload, it is linkable, back/forward work,
   and — unlike a path route — it needs no server rewrite, so a reload on
   #/studio still gets index.html from the static mount in api/main.py rather
   than a 404. */

/** The current route, e.g. `'/studio'`. `'/'` when the hash is empty. */
export function useHashRoute(): string {
  const read = () => {
    const h = window.location.hash.replace(/^#/, '')
    return h.startsWith('/') ? h : '/'
  }
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const on = () => setRoute(read())
    window.addEventListener('hashchange', on)
    // The hash may already differ from our initial read if something changed it
    // between render and effect (a deep link restored by the browser).
    on()
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

/** Navigate. Setting the hash fires `hashchange`, so state follows on its own. */
export function useNavigate() {
  return useCallback((route: string) => {
    window.location.hash = route === '/' ? '' : `#${route}`
    window.scrollTo({ top: 0 })
  }, [])
}
