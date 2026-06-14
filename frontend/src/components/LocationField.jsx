import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const COORD_RE = /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/

// ccTLD region bias for geocoding, derived from the browser locale
// (e.g. "en-US" -> "us"), so "3 hampshire st" prefers nearby matches.
const REGION = (navigator.language?.split('-')[1] || '').toLowerCase()

export default function LocationField({ label, value, onChange, labelAction, invalid, name }) {
  const [query, setQuery] = useState(value?.label ?? '')
  const [candidates, setCandidates] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const debounceRef = useRef(null)

  // Follow external changes to `value` (e.g. swapping From/To, or loading a
  // saved route) so the displayed text stays in sync with the confirmed point.
  useEffect(() => {
    if (value && value.label !== query) {
      setQuery(value.label)
      setCandidates(null)
      setError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value?.lat, value?.lng, value?.label])

  function select(candidate) {
    onChange(candidate)
    setQuery(candidate.label)
    setCandidates(null)
    setError(null)
  }

  async function search(q) {
    const coords = q.match(COORD_RE)
    if (coords) {
      const lat = parseFloat(coords[1])
      const lng = parseFloat(coords[2])
      if (Math.abs(lat) > 90 || Math.abs(lng) > 180) {
        setError('Coordinates out of range.')
        return
      }
      select({ lat, lng, label: `${lat.toFixed(5)}, ${lng.toFixed(5)}` })
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await api.geocode(q, REGION)
      const list = res.results.map((r) => ({ lat: r.lat, lng: r.lng, label: r.address }))
      setCandidates(list)
      if (list.length === 0) setError('No matches found — try adding a city or state.')
    } catch (e) {
      setError(e.message)
      setCandidates(null)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    clearTimeout(debounceRef.current)
    const q = query.trim()
    if (q.length < 4 || (value && q === value.label)) {
      setCandidates(null)
      return
    }
    debounceRef.current = setTimeout(() => search(q), 600)
    return () => clearTimeout(debounceRef.current)
  }, [query]) // eslint-disable-line react-hooks/exhaustive-deps

  function onInput(e) {
    setQuery(e.target.value)
    if (value) onChange(null) // editing invalidates the confirmed location
  }

  function onKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault()
      clearTimeout(debounceRef.current)
      search(query.trim())
    }
    if (e.key === 'Escape') setCandidates(null)
  }

  return (
    <div className="relative">
      <div className="mb-1 flex items-center justify-between">
        <label
          htmlFor={name}
          className="block text-xs font-semibold uppercase tracking-wide text-slate-500"
        >
          {label}
        </label>
        {labelAction}
      </div>
      {/* Distinct name/id + a section-scoped address token so password managers
          (1Password) and the browser treat From and To as separate address
          fields rather than filling only the first. */}
      <input
        id={name}
        name={name}
        autoComplete={name ? `section-${name} street-address` : 'off'}
        value={query}
        onChange={onInput}
        onKeyDown={onKeyDown}
        onBlur={() => setTimeout(() => setCandidates(null), 200)}
        placeholder="Address or lat,lng"
        className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none ${
          invalid && value
            ? 'border-red-400 focus:border-red-500'
            : value
              ? 'border-emerald-400 focus:border-emerald-500'
              : 'border-slate-300 focus:border-blue-500'
        }`}
      />
      {busy && (
        <p className="mt-1 text-xs text-slate-500">Searching…</p>
      )}
      {candidates && candidates.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {candidates.map((c, i) => (
            <li key={i}>
              <button
                type="button"
                onMouseDown={() => select(c)}
                className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-blue-50"
              >
                {c.label}
                <span className="block text-xs text-slate-400">
                  {c.lat.toFixed(4)}, {c.lng.toFixed(4)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      {value ? (
        <p
          className={`mt-1 text-xs ${
            invalid ? 'font-bold text-red-600' : 'text-emerald-700'
          }`}
          title={value.label}
        >
          {invalid ? '⚠' : '✓'} {value.lat.toFixed(5)}, {value.lng.toFixed(5)}
        </p>
      ) : (
        query.trim().length >= 4 &&
        !busy &&
        !candidates && (
          <p className="mt-1 text-xs text-amber-600">
            Pick a match from the list to confirm this location.
          </p>
        )
      )}
    </div>
  )
}
