export function haversineKm(a, b) {
  const toRad = (d) => (d * Math.PI) / 180
  const R = 6371
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export const KM_TO_MILES = 0.621371

// Straight-line distance beyond which two points are implausible as a commute
// (almost always a wrong geocode).
export const MAX_COMMUTE_MILES = 100

// True only when both points are set AND they're too far apart to be a commute.
export function isCommuteTooFar(origin, destination) {
  if (!origin || !destination) return false
  return haversineKm(origin, destination) * KM_TO_MILES > MAX_COMMUTE_MILES
}
