import LocationField from './LocationField'
import { PALETTES } from '../palettes'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const INTERVALS = [15, 30]
const HOURS = Array.from({ length: 24 }, (_, h) => h)

function hourLabel(h) {
  const ampm = h < 12 ? 'AM' : 'PM'
  const display = h % 12 === 0 ? 12 : h % 12
  return `${display}:00 ${ampm}`
}

export default function Sidebar({ params, onChange, onRun, running, estimatedCalls }) {
  const set = (patch) => onChange({ ...params, ...patch })

  function toggleDay(day) {
    const days = params.days.includes(day)
      ? params.days.filter((d) => d !== day)
      : [...params.days, day].sort()
    set({ days })
  }

  const ready =
    params.origin && params.destination && params.days.length > 0 && !running

  return (
    <aside className="w-full shrink-0 space-y-5 border-b border-slate-200 bg-white p-4 shadow-sm lg:h-screen lg:w-80 lg:overflow-y-auto lg:border-b-0 lg:border-r">
      <h2 className="text-lg font-bold text-slate-800">Route & Parameters</h2>

      <LocationField
        label="From (origin)"
        value={params.origin}
        onChange={(origin) => set({ origin })}
      />
      <LocationField
        label="To (destination)"
        value={params.destination}
        onChange={(destination) => set({ destination })}
      />

      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
          Analysis vector
        </label>
        <div className="grid grid-cols-2 gap-2">
          {[
            ['departure', 'Depart at'],
            ['arrival', 'Arrive by'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => set({ vector: value })}
              className={`rounded-lg border px-3 py-2 text-sm font-medium ${
                params.vector === value
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-slate-300 text-slate-600 hover:bg-slate-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            From hour
          </label>
          <select
            value={params.startHour}
            onChange={(e) => {
              const startHour = Number(e.target.value)
              set({ startHour, endHour: Math.max(startHour, params.endHour) })
            }}
            className="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
          >
            {HOURS.map((h) => (
              <option key={h} value={h}>
                {hourLabel(h)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            To hour
          </label>
          <select
            value={params.endHour}
            onChange={(e) => set({ endHour: Number(e.target.value) })}
            className="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
          >
            {HOURS.filter((h) => h >= params.startHour).map((h) => (
              <option key={h} value={h}>
                {hourLabel(h)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
          Interval step
        </label>
        <div className="grid grid-cols-4 gap-2">
          {INTERVALS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => set({ intervalMinutes: m })}
              className={`rounded-lg border px-2 py-2 text-sm font-medium ${
                params.intervalMinutes === m
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-slate-300 text-slate-600 hover:bg-slate-50'
              }`}
            >
              {m}m
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
          Days of week
        </label>
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-7 lg:grid-cols-4">
          {DAYS.map((name, day) => (
            <label
              key={name}
              className={`flex cursor-pointer items-center justify-center gap-1 rounded-lg border px-1 py-2 text-xs font-medium ${
                params.days.includes(day)
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-slate-300 text-slate-600 hover:bg-slate-50'
              }`}
            >
              <input
                type="checkbox"
                checked={params.days.includes(day)}
                onChange={() => toggleDay(day)}
                className="sr-only"
              />
              {name}
            </label>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
          Color scheme
        </label>
        <select
          value={params.palette}
          onChange={(e) => set({ palette: e.target.value })}
          className="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
        >
          {Object.entries(PALETTES).map(([key, p]) => (
            <option key={key} value={key}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2 border-t border-slate-200 pt-4">
        <button
          type="button"
          onClick={onRun}
          disabled={!ready}
          className="w-full rounded-lg bg-blue-600 py-2.5 font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {running ? 'Analyzing…' : 'Run analysis'}
        </button>
        <p className="text-center text-xs text-slate-500">
          Up to {estimatedCalls} Google API calls — cache hits reduce this.
        </p>
      </div>
    </aside>
  )
}
