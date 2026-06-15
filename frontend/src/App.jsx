import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { isCommuteTooFar } from './utils/geo'
import {
  clampParamsToTier,
  isTooFarForTier,
  maxDistanceMiles,
  tierLimits,
} from './utils/tiers'
import { useAuth } from './auth/AuthContext'
import SetupWizard from './components/SetupWizard'
import Sidebar from './components/Sidebar'
import CommuteChart from './components/CommuteChart'
import RoutePreview from './components/RoutePreview'
import AccountBar from './components/AccountBar'

const DEFAULT_PARAMS = {
  origin: null,
  destination: null,
  vector: 'departure',
  startHour: 7,
  endHour: 9,
  intervalMinutes: 15,
  days: [0, 1, 2, 3, 4],
  palette: 'okabeIto',
}

export default function App() {
  const { ready: authReady, mapsConfigured, setMapsConfigured, tier, tierMatrix } = useAuth()
  const [skipped] = useState(() => !!localStorage.getItem('setupSkipped'))
  const [params, setParams] = useState(DEFAULT_PARAMS)
  const limits = useMemo(() => tierLimits(tierMatrix, tier), [tierMatrix, tier])

  // Keep params within the current tier (e.g. clamp ANON to 60m / 2 weekdays),
  // re-running whenever the tier or its matrix changes (sign-in/out).
  useEffect(() => {
    if (tierMatrix) setParams((p) => clampParamsToTier(p, tierMatrix, tier))
  }, [tier, tierMatrix])
  const [results, setResults] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [highlightDay, setHighlightDay] = useState(null)

  const setupState = !authReady ? 'loading' : mapsConfigured || skipped ? 'ready' : 'needed'

  function applyRoute(routeParams) {
    setParams((p) => ({ ...p, ...routeParams }))
    setResults(null)
  }

  function applyAddress(which, addr) {
    const point = { lat: addr.lat, lng: addr.lng, label: addr.address }
    setParams((p) => ({ ...p, [which]: point }))
  }

  const estimatedCalls = useMemo(() => {
    const slots =
      Math.floor(((params.endHour - params.startHour) * 60) / params.intervalMinutes) + 1
    const perPoint = params.vector === 'arrival' ? 4 : 3
    return slots * params.days.length * perPoint
  }, [params])

  // Too far apart: a wrong geocode, or beyond the tier's max trip distance.
  // Uses the tier limit when the matrix has loaded; falls back to the flat
  // 100-mile sanity check otherwise.
  const tooFar = useMemo(
    () =>
      limits
        ? isTooFarForTier(limits, params.origin, params.destination)
        : isCommuteTooFar(params.origin, params.destination),
    [limits, params.origin, params.destination]
  )

  async function runAnalysis() {
    setError(null)
    setRunning(true)
    setResults(null)
    setHighlightDay(null)
    try {
      const data = await api.analyze({
        origin: { lat: params.origin.lat, lng: params.origin.lng },
        destination: { lat: params.destination.lat, lng: params.destination.lng },
        vector: params.vector,
        start_hour: params.startHour,
        end_hour: params.endHour,
        interval_minutes: params.intervalMinutes,
        days: params.days,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      })
      setResults(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  if (setupState === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center text-slate-500">
        Loading…
      </div>
    )
  }

  if (setupState === 'needed') {
    return (
      <SetupWizard
        onConfigured={() => setMapsConfigured(true)}
        onSkip={() => {
          localStorage.setItem('setupSkipped', '1')
          // Force re-render via params (skipped is read once); reload is simplest.
          window.location.reload()
        }}
      />
    )
  }

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:flex-row">
      <Sidebar
        params={params}
        onChange={setParams}
        onRun={runAnalysis}
        running={running}
        estimatedCalls={estimatedCalls}
        tooFar={tooFar}
        tier={tier}
        tierMatrix={tierMatrix}
        onApplyRoute={applyRoute}
        onApplyAddress={applyAddress}
      />
      <main className="flex min-h-[60vh] flex-1 flex-col gap-4 p-4 lg:overflow-y-auto">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-800">
              Traffinator
              <span className="ml-2 text-sm font-medium italic text-slate-400">
                "I'll be fast."
              </span>
            </h1>
            <p className="text-sm text-slate-500">
              Predictive drive-time trends by day of week, with min–max confidence bands.
              Click or hover a day in the legend to highlight it.
            </p>
          </div>
          <AccountBar />
        </header>

        {error && (
          <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <RoutePreview
          origin={params.origin}
          destination={params.destination}
          maxMiles={maxDistanceMiles(limits)}
        />

        {running && (
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700">
            Running analysis… cache misses are fetched live from Google Maps, so the
            first run can take a while.
          </div>
        )}

        {results ? (
          <>
            <div className="flex flex-wrap gap-3 text-xs text-slate-600">
              <span className="rounded-full bg-white px-3 py-1 shadow-sm">
                {results.meta.total_points} data points
              </span>
              <span className="rounded-full bg-white px-3 py-1 shadow-sm">
                {results.meta.cache_hits} served from cache
              </span>
              <span className="rounded-full bg-white px-3 py-1 shadow-sm">
                {results.meta.api_calls} Google API calls
              </span>
              {results.meta.errors.length > 0 && (
                <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-800 shadow-sm">
                  {results.meta.errors.length} points failed
                </span>
              )}
            </div>
            {results.meta.errors.length > 0 && (
              <details className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                <summary className="cursor-pointer font-medium">
                  Why did {results.meta.errors.length} point
                  {results.meta.errors.length > 1 ? 's' : ''} fail?
                </summary>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {[...new Set(results.meta.errors.map((e) => e.error))].map((msg) => (
                    <li key={msg}>
                      {msg}
                      {' — '}
                      {results.meta.errors.filter((e) => e.error === msg).length} point(s)
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <div className="min-h-[420px] flex-1 rounded-xl bg-white p-4 shadow">
              <CommuteChart
                results={results}
                paletteKey={params.palette}
                highlightDay={highlightDay}
                onHighlightDay={setHighlightDay}
              />
            </div>
          </>
        ) : (
          !running && (
            <div className="flex flex-1 flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-slate-300 text-slate-400">
              <span>Set your route and parameters in the sidebar, then run the analysis.</span>
              <span className="text-xs">Hasta la vista, gridlock.</span>
            </div>
          )
        )}
      </main>
    </div>
  )
}
