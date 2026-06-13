import { useState } from 'react'
import { api } from '../api'

export default function SetupWizard({ onConfigured, onSkip }) {
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function save(e) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.saveSetup(apiKey)
      onConfigured()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-lg">
        <h1 className="text-2xl font-bold text-slate-800">
          Welcome to Traffinator
          <span className="ml-2 text-base font-medium italic text-slate-400">
            "I'll be fast."
          </span>
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          One-time setup: a Google Maps API key is required to fetch predictive
          traffic data. The key is validated, then stored in the app database
          (an environment variable <code className="rounded bg-slate-100 px-1">GOOGLE_MAPS_API_KEY</code>{' '}
          always takes precedence if set).
        </p>
        <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm text-slate-600">
          <li>
            Create a key in the{' '}
            <a
              className="text-blue-600 underline"
              href="https://console.cloud.google.com/google/maps-apis/credentials"
              target="_blank"
              rel="noreferrer"
            >
              Google Cloud Console
            </a>{' '}
            (billing must be enabled).
          </li>
          <li>
            Enable the <strong>Distance Matrix API</strong> and the{' '}
            <strong>Geocoding API</strong> on the project.
          </li>
          <li>Paste the key below.</li>
        </ol>
        <form onSubmit={save} className="mt-6 space-y-4">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="AIza…"
            required
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          {error && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={saving || !apiKey.trim()}
            className="w-full rounded-lg bg-blue-600 py-2 font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Validating key…' : 'Validate & save'}
          </button>
        </form>
        <button
          type="button"
          onClick={onSkip}
          className="mt-4 w-full text-center text-xs text-slate-500 underline hover:text-slate-700"
        >
          Continue without a key (cached/demo data only — geocoding and live
          traffic fetches will be unavailable)
        </button>
      </div>
    </div>
  )
}
