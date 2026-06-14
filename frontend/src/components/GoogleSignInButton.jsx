import { useEffect, useRef } from 'react'

const GIS_SRC = 'https://accounts.google.com/gsi/client'

function loadGis() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve()
    const existing = document.querySelector(`script[src="${GIS_SRC}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', reject)
      return
    }
    const script = document.createElement('script')
    script.src = GIS_SRC
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = reject
    document.head.appendChild(script)
  })
}

export default function GoogleSignInButton({ clientId, onCredential, onError }) {
  const ref = useRef(null)

  useEffect(() => {
    if (!clientId) return
    let cancelled = false
    loadGis()
      .then(() => {
        if (cancelled || !ref.current) return
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (resp) => onCredential(resp.credential),
        })
        window.google.accounts.id.renderButton(ref.current, {
          theme: 'outline',
          size: 'large',
          text: 'signin_with',
          width: 240,
        })
      })
      .catch(() => onError?.('Could not load Google sign-in.'))
    return () => {
      cancelled = true
    }
  }, [clientId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!clientId) {
    return (
      <p className="text-xs text-slate-400">
        Google sign-in isn't configured on the server.
      </p>
    )
  }
  return <div ref={ref} />
}
