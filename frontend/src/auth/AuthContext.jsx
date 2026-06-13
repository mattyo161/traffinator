import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, auth as tokenStore } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [googleClientId, setGoogleClientId] = useState('')
  const [appleEnabled, setAppleEnabled] = useState(false)
  const [mapsConfigured, setMapsConfigured] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    async function init() {
      try {
        const cfg = await api.config()
        setGoogleClientId(cfg.google_oauth_client_id || '')
        setAppleEnabled(!!cfg.apple_oauth_enabled)
        setMapsConfigured(!!cfg.configured)
      } catch {
        /* backend unreachable; surfaced elsewhere */
      }
      if (tokenStore.token) {
        try {
          const r = await api.me()
          if (r.authenticated) setUser(r.user)
          else tokenStore.token = null
        } catch {
          tokenStore.token = null
        }
      }
      setReady(true)
    }
    init()
  }, [])

  async function loginWithGoogle(credential) {
    const r = await api.googleLogin(credential)
    tokenStore.token = r.token
    setUser(r.user)
    return r.user
  }

  async function logout() {
    try {
      await api.logout()
    } catch {
      /* best effort */
    }
    tokenStore.token = null
    setUser(null)
  }

  const value = {
    user,
    googleClientId,
    appleEnabled,
    mapsConfigured,
    setMapsConfigured,
    ready,
    loginWithGoogle,
    logout,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
