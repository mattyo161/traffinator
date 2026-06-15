// Pure helpers that turn the tier→limits matrix from GET /api/config into the
// availability/upsell decisions the UI renders. Kept free of React so they can
// be unit-tested directly (see tiers.test.js). The backend enforces the same
// matrix (commute/tiers.py) — these only decide what to gray out and clamp.
import { haversineKm, KM_TO_MILES } from './geo'

export function tierLimits(config, tier) {
  return config?.limits?.[tier] || null
}

// One {minutes, enabled, comingSoon} entry per interval the UI knows about.
export function intervalOptions(config, tier) {
  const all = config?.intervals_all || []
  const comingSoon = new Set(config?.intervals_coming_soon || [])
  const enabled = new Set(tierLimits(config, tier)?.intervals || [])
  return all.map((minutes) => ({
    minutes,
    comingSoon: comingSoon.has(minutes),
    enabled: enabled.has(minutes) && !comingSoon.has(minutes),
  }))
}

// Upsell prompt for a control the current tier can't use.
export function upsellMessage(config, tier) {
  const next = config?.next_tier?.[tier]
  if (next === 'FREE') return 'Sign in for a free account to unlock this.'
  if (next === 'PRO') return 'Upgrade to PRO to unlock this.'
  return 'Not available on your plan.'
}

export function dayAllowed(limits, day) {
  return (limits?.days_allowed || [0, 1, 2, 3, 4, 5, 6]).includes(day)
}

export function maxDays(limits) {
  return limits?.days_max ?? 7
}

export function allowedFromHours(limits) {
  return limits?.from_hours || Array.from({ length: 24 }, (_, h) => h)
}

export function fromHourAllowed(limits, hour) {
  return allowedFromHours(limits).includes(hour)
}

export function maxToSpan(limits) {
  return limits?.to_span_max ?? 23
}

// Highest selectable To hour given a From hour (span cap, clamped to 23).
export function maxEndHour(limits, startHour) {
  return Math.min(23, startHour + maxToSpan(limits))
}

export function maxDistanceMiles(limits) {
  return limits?.max_distance_mi ?? null
}

// True when two set points exceed the tier's max origin↔dest distance.
export function isTooFarForTier(limits, origin, destination) {
  if (!origin || !destination) return false
  const max = maxDistanceMiles(limits)
  if (max == null) return false
  return haversineKm(origin, destination) * KM_TO_MILES > max
}

// Coerce analysis params into what the tier allows, so the initial/persisted
// state is valid (and Run isn't blocked) when the tier loads or changes.
export function clampParamsToTier(params, config, tier) {
  const limits = tierLimits(config, tier)
  if (!limits) return params

  let { intervalMinutes, days, startHour, endHour } = params

  const opts = intervalOptions(config, tier)
  if (!opts.some((o) => o.minutes === intervalMinutes && o.enabled)) {
    const firstEnabled = opts.find((o) => o.enabled)
    if (firstEnabled) intervalMinutes = firstEnabled.minutes
  }

  days = days.filter((d) => dayAllowed(limits, d)).slice(0, maxDays(limits))

  if (!fromHourAllowed(limits, startHour)) {
    startHour = allowedFromHours(limits)[0] ?? startHour
  }
  endHour = Math.min(Math.max(endHour, startHour), maxEndHour(limits, startHour))

  if (
    intervalMinutes === params.intervalMinutes &&
    days.length === params.days.length &&
    days.every((d, i) => d === params.days[i]) &&
    startHour === params.startHour &&
    endHour === params.endHour
  ) {
    return params // unchanged — preserve referential identity
  }
  return { ...params, intervalMinutes, days, startHour, endHour }
}
