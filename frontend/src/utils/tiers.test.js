import { describe, expect, it } from 'vitest'
import {
  clampParamsToTier,
  dayAllowed,
  intervalOptions,
  isTooFarForTier,
  maxEndHour,
  tierLimits,
  upsellMessage,
} from './tiers'

const HOURS = Array.from({ length: 24 }, (_, h) => h)

// Mirrors the shape of GET /api/config -> config.tiers (commute/tiers.py).
const CONFIG = {
  intervals_all: [60, 30, 15, 5],
  intervals_coming_soon: [5],
  next_tier: { ANON: 'FREE', FREE: 'PRO', PRO: null },
  limits: {
    ANON: {
      intervals: [60], days_allowed: [0, 1, 2, 3, 4], days_max: 2,
      from_hours: [5, 6, 7, 8, 9, 15, 16, 17, 18, 19], to_span_max: 2, max_distance_mi: 50,
    },
    FREE: {
      intervals: [60, 30], days_allowed: [0, 1, 2, 3, 4], days_max: 5,
      from_hours: HOURS, to_span_max: 4, max_distance_mi: 100,
    },
    PRO: {
      intervals: [60, 30, 15], days_allowed: [0, 1, 2, 3, 4, 5, 6], days_max: 7,
      from_hours: HOURS, to_span_max: 6, max_distance_mi: 500,
    },
  },
}

const BOSTON = { lat: 42.3601, lng: -71.0589 }
const NYC = { lat: 40.7128, lng: -74.006 }
const NEWTON = { lat: 42.2968, lng: -71.2127 }

describe('intervalOptions', () => {
  it('marks 5m coming-soon and the rest by tier', () => {
    const anon = intervalOptions(CONFIG, 'ANON')
    expect(anon.find((o) => o.minutes === 60)).toMatchObject({ enabled: true, comingSoon: false })
    expect(anon.find((o) => o.minutes === 30)).toMatchObject({ enabled: false })
    expect(anon.find((o) => o.minutes === 5)).toMatchObject({ enabled: false, comingSoon: true })

    const pro = intervalOptions(CONFIG, 'PRO')
    expect(pro.find((o) => o.minutes === 15).enabled).toBe(true)
    expect(pro.find((o) => o.minutes === 5).comingSoon).toBe(true) // never enabled
  })
})

describe('upsellMessage', () => {
  it('points at the next tier', () => {
    expect(upsellMessage(CONFIG, 'ANON')).toMatch(/sign in/i)
    expect(upsellMessage(CONFIG, 'FREE')).toMatch(/upgrade to pro/i)
    expect(upsellMessage(CONFIG, 'PRO')).toMatch(/not available/i)
  })
})

describe('day + hour limits', () => {
  it('gates weekend days below PRO', () => {
    expect(dayAllowed(tierLimits(CONFIG, 'ANON'), 5)).toBe(false)
    expect(dayAllowed(tierLimits(CONFIG, 'ANON'), 0)).toBe(true)
    expect(dayAllowed(tierLimits(CONFIG, 'PRO'), 6)).toBe(true)
  })

  it('caps the To hour by span', () => {
    expect(maxEndHour(tierLimits(CONFIG, 'ANON'), 5)).toBe(7)
    expect(maxEndHour(tierLimits(CONFIG, 'FREE'), 8)).toBe(12)
    expect(maxEndHour(tierLimits(CONFIG, 'PRO'), 8)).toBe(14)
  })
})

describe('isTooFarForTier', () => {
  it('uses the tier max distance', () => {
    // Boston–NYC is ~190 mi: over ANON's 50, under PRO's 500.
    expect(isTooFarForTier(tierLimits(CONFIG, 'ANON'), BOSTON, NYC)).toBe(true)
    expect(isTooFarForTier(tierLimits(CONFIG, 'PRO'), BOSTON, NYC)).toBe(false)
    expect(isTooFarForTier(tierLimits(CONFIG, 'ANON'), BOSTON, NEWTON)).toBe(false)
  })

  it('is false when an endpoint is missing', () => {
    expect(isTooFarForTier(tierLimits(CONFIG, 'ANON'), null, NYC)).toBe(false)
  })
})

describe('clampParamsToTier', () => {
  const base = { intervalMinutes: 15, days: [0, 1, 2, 3, 4], startHour: 7, endHour: 9 }

  it('forces ANON to 60m, 2 days, and a valid window', () => {
    const out = clampParamsToTier(base, CONFIG, 'ANON')
    expect(out.intervalMinutes).toBe(60)
    expect(out.days).toEqual([0, 1])
    expect(out.startHour).toBe(7) // already in the ANON morning window
    expect(out.endHour).toBe(9) // span 2 ok
  })

  it('moves an out-of-window ANON From hour to the first allowed', () => {
    const out = clampParamsToTier({ ...base, startHour: 12, endHour: 13 }, CONFIG, 'ANON')
    expect(out.startHour).toBe(5)
    expect(out.endHour).toBeLessThanOrEqual(maxEndHour(tierLimits(CONFIG, 'ANON'), 5))
  })

  it('keeps a valid FREE selection (30m, 5 weekdays)', () => {
    const free = { intervalMinutes: 30, days: [0, 1, 2, 3, 4], startHour: 8, endHour: 12 }
    expect(clampParamsToTier(free, CONFIG, 'FREE')).toBe(free) // unchanged identity
  })

  it('returns the same object when nothing needs clamping (PRO)', () => {
    const pro = { intervalMinutes: 15, days: [5, 6], startHour: 8, endHour: 14 }
    expect(clampParamsToTier(pro, CONFIG, 'PRO')).toBe(pro)
  })
})
