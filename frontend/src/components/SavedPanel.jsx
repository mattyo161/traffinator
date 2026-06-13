import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'

export default function SavedPanel({ params, onApplyRoute, onApplyAddress }) {
  const { user } = useAuth()
  const [routes, setRoutes] = useState([])
  const [addresses, setAddresses] = useState([])
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!user) return
    try {
      const [r, a] = await Promise.all([api.listRoutes(), api.listAddresses()])
      setRoutes(r)
      setAddresses(a)
    } catch (e) {
      setError(e.message)
    }
  }, [user])

  useEffect(() => {
    refresh()
  }, [refresh])

  if (!user) {
    return (
      <div className="border-t border-slate-200 pt-4 text-xs text-slate-500">
        Sign in (top right) to save commutes and places.
      </div>
    )
  }

  async function saveCurrentRoute() {
    setError(null)
    if (!params.origin || !params.destination) {
      setError('Set both From and To before saving.')
      return
    }
    const name = window.prompt('Name this commute:', 'My commute')
    if (!name) return
    try {
      await api.createRoute({
        name,
        origin_label: params.origin.label,
        origin_lat: params.origin.lat,
        origin_lng: params.origin.lng,
        dest_label: params.destination.label,
        dest_lat: params.destination.lat,
        dest_lng: params.destination.lng,
        params: {
          vector: params.vector,
          startHour: params.startHour,
          endHour: params.endHour,
          intervalMinutes: params.intervalMinutes,
          days: params.days,
          palette: params.palette,
        },
      })
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  async function saveCurrentPlace(which) {
    setError(null)
    const point = which === 'origin' ? params.origin : params.destination
    if (!point) {
      setError(`Set the ${which === 'origin' ? 'From' : 'To'} location first.`)
      return
    }
    const label = window.prompt('Name this place:', point.label.split(',')[0])
    if (!label) return
    try {
      await api.createAddress({ label, address: point.label, lat: point.lat, lng: point.lng })
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  function loadRoute(r) {
    onApplyRoute({
      origin: { lat: r.origin_lat, lng: r.origin_lng, label: r.origin_label },
      destination: { lat: r.dest_lat, lng: r.dest_lng, label: r.dest_label },
      ...r.params,
    })
  }

  return (
    <div className="space-y-3 border-t border-slate-200 pt-4">
      {error && <p className="text-xs text-red-600">{error}</p>}

      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Saved commutes
          </span>
          <button
            type="button"
            onClick={saveCurrentRoute}
            className="text-xs font-medium text-blue-600 hover:underline"
          >
            + Save current
          </button>
        </div>
        {routes.length === 0 ? (
          <p className="text-xs text-slate-400">No saved commutes yet.</p>
        ) : (
          <ul className="space-y-1">
            {routes.map((r) => (
              <li key={r.id} className="flex items-center gap-2 text-sm">
                <button
                  type="button"
                  onClick={() => loadRoute(r)}
                  className="min-w-0 flex-1 truncate rounded px-2 py-1 text-left hover:bg-slate-100"
                  title={`${r.origin_label} → ${r.dest_label}`}
                >
                  {r.name}
                </button>
                <button
                  type="button"
                  onClick={() => api.deleteRoute(r.id).then(refresh)}
                  className="shrink-0 text-xs text-slate-400 hover:text-red-600"
                  aria-label={`Delete ${r.name}`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Saved places
          </span>
          <span className="flex gap-2 text-xs">
            <button
              type="button"
              onClick={() => saveCurrentPlace('origin')}
              className="font-medium text-blue-600 hover:underline"
            >
              + From
            </button>
            <button
              type="button"
              onClick={() => saveCurrentPlace('destination')}
              className="font-medium text-blue-600 hover:underline"
            >
              + To
            </button>
          </span>
        </div>
        {addresses.length === 0 ? (
          <p className="text-xs text-slate-400">No saved places yet.</p>
        ) : (
          <ul className="space-y-1">
            {addresses.map((a) => (
              <li key={a.id} className="flex items-center gap-1 text-sm">
                <span className="min-w-0 flex-1 truncate" title={a.address}>
                  {a.label}
                </span>
                <button
                  type="button"
                  onClick={() => onApplyAddress('origin', a)}
                  className="shrink-0 rounded border border-slate-300 px-1.5 py-0.5 text-xs hover:bg-slate-100"
                >
                  From
                </button>
                <button
                  type="button"
                  onClick={() => onApplyAddress('destination', a)}
                  className="shrink-0 rounded border border-slate-300 px-1.5 py-0.5 text-xs hover:bg-slate-100"
                >
                  To
                </button>
                <button
                  type="button"
                  onClick={() => api.deleteAddress(a.id).then(refresh)}
                  className="shrink-0 text-xs text-slate-400 hover:text-red-600"
                  aria-label={`Delete ${a.label}`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
