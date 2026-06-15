import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import GoogleSignInButton from './GoogleSignInButton'

export default function AccountBar() {
  const { user, tier, googleClientId, appleEnabled, loginWithGoogle, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState(null)

  async function handleCredential(credential) {
    setError(null)
    try {
      await loginWithGoogle(credential)
      setOpen(false)
    } catch (e) {
      setError(e.message)
    }
  }

  if (user) {
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="text-slate-600">
          Signed in as <span className="font-medium">{user.name}</span>
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
            tier === 'PRO'
              ? 'bg-amber-100 text-amber-700'
              : 'bg-slate-100 text-slate-500'
          }`}
        >
          {tier}
        </span>
        <button
          type="button"
          onClick={logout}
          className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          Sign out
        </button>
      </div>
    )
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-900"
      >
        Sign in to save routes
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-slate-200 bg-white p-4 shadow-lg">
          <p className="mb-3 text-sm text-slate-600">
            Sign in to save commutes and addresses across sessions.
          </p>
          <GoogleSignInButton
            clientId={googleClientId}
            onCredential={handleCredential}
            onError={setError}
          />
          {appleEnabled ? (
            <p className="mt-2 text-xs text-slate-400">Apple sign-in available.</p>
          ) : (
            <p className="mt-2 text-xs text-slate-400">Apple sign-in coming soon.</p>
          )}
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </div>
      )}
    </div>
  )
}
