import { describe, expect, it } from 'vitest'
import { haversineKm, isCommuteTooFar } from './geo'

const BOSTON = { lat: 42.3601, lng: -71.0589 }
const NYC = { lat: 40.7128, lng: -74.006 }
const LA = { lat: 34.0522, lng: -118.2437 }
const MELBOURNE_SUBURB = { lat: -38.0718634, lng: 145.4348288 }
const NEWTON_MA = { lat: 42.2968347, lng: -71.2126949 }

describe('haversineKm', () => {
  it('returns 0 for identical points', () => {
    expect(haversineKm(BOSTON, BOSTON)).toBe(0)
  })

  it('is symmetric', () => {
    expect(haversineKm(BOSTON, NYC)).toBeCloseTo(haversineKm(NYC, BOSTON), 9)
  })

  it('matches the known NYC-LA distance (~3936 km)', () => {
    const d = haversineKm(NYC, LA)
    expect(d).toBeGreaterThan(3900)
    expect(d).toBeLessThan(3970)
  })

  it('flags the Australia-to-Boston mixup as far beyond any commute', () => {
    // The geocoding bug that motivated the route-preview warning
    const d = haversineKm(MELBOURNE_SUBURB, NEWTON_MA)
    expect(d).toBeGreaterThan(16000)
  })
})

describe('isCommuteTooFar', () => {
  it('is false when either endpoint is missing', () => {
    expect(isCommuteTooFar(null, NEWTON_MA)).toBe(false)
    expect(isCommuteTooFar(BOSTON, null)).toBe(false)
    expect(isCommuteTooFar(null, null)).toBe(false)
  })

  it('is false for a plausible local commute (Boston <-> Newton)', () => {
    expect(isCommuteTooFar(BOSTON, NEWTON_MA)).toBe(false)
  })

  it('is true for clearly-too-far points (Boston <-> NYC, ~300km)', () => {
    expect(isCommuteTooFar(BOSTON, NYC)).toBe(true)
  })

  it('is true for the Australia-to-Boston geocode mixup', () => {
    expect(isCommuteTooFar(MELBOURNE_SUBURB, NEWTON_MA)).toBe(true)
  })
})
