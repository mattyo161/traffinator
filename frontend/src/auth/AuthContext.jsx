import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, auth as tokenStore } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [googleClientId, setGoogleClientId] = useState('')
  const [appleEnabled, setAppleEnabled] = useState(false)
  const [mapsConfigured, setMapsConfigured] = useState(false)
  // Tier gating: the requester's current tier + the full limits matrix, both
  // from GET /api/config. Re-fetched on login/logout since the tier changes
  // (ANON -> FREE on sign-in). The UI grays out / clamps from `tierMatrix`.
  const [tier, setTier] = useState('ANON')
  const [tierMatrix, setTierMatrix] = useState(null)
  const [ready, setReady] = useState(false)

  const applyConfig = useCallback((cfg) => {
    setGoogleClientId(cfg.google_oauth_client_id || '')
    setAppleEnabled(!!cfg.apple_oauth_enabled)
    setMapsConfigured(!!cfg.configured)
    setTier(cfg.tier || 'ANON')
    if (cfg.tiers) setTierMatrix(cfg.tiers)
  }, [])

  const refreshConfig = useCallback(async () => {
    try {
      applyConfig(await api.config())
    } catch {
      /* backend unreachable; surfaced elsewhere */
    }
  }, [applyConfig])

  useEffect(() => {
    async function init() {
      await refreshConfig()
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
  }, [refreshConfig])

  async function loginWithGoogle(credential) {
    const r = await api.googleLogin(credential)
    tokenStore.token = r.token
    setUser(r.user)
    await refreshConfig() // tier likely changed ANON -> FREE/PRO
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
    await refreshConfig() // back to ANON limits
  }

  const value = {
    user,
    googleClientId,
    appleEnabled,
    mapsConfigured,
    setMapsConfigured,
    tier,
    tierMatrix,
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
