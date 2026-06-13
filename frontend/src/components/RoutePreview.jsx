import { useEffect, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Polyline,
  Tooltip as LeafletTooltip,
  useMap,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { haversineKm, KM_TO_MILES } from '../utils/geo'
import { api } from '../api'

// Beyond this, the points almost certainly aren't a commute (wrong geocode?)
const SUSPICIOUS_KM = 150

function FitBounds({ bounds }) {
  const map = useMap()
  const key = JSON.stringify(bounds)
  useEffect(() => {
    if (bounds.length === 1) {
      map.setView(bounds[0], 13)
    } else if (bounds.length > 1) {
      map.fitBounds(L.latLngBounds(bounds), { padding: [40, 40] })
    }
  }, [key, map]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

export default function RoutePreview({ origin, destination }) {
  const [route, setRoute] = useState(null) // { geometry: [[lat,lng]], distance_m }
  const [routeError, setRouteError] = useState(null)

  useEffect(() => {
    setRoute(null)
    setRouteError(null)
    if (!origin || !destination) return
    let cancelled = false
    api
      .route(
        { lat: origin.lat, lng: origin.lng },
        { lat: destination.lat, lng: destination.lng }
      )
      .then((r) => {
        if (!cancelled) setRoute(r)
      })
      .catch((e) => {
        if (!cancelled) setRouteError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [origin?.lat, origin?.lng, destination?.lat, destination?.lng])

  const endpoints = [origin, destination].filter(Boolean).map((p) => [p.lat, p.lng])
  if (endpoints.length === 0) return null

  // Prefer the real driving distance; fall back to straight-line.
  const straightKm = origin && destination ? haversineKm(origin, destination) : null
  const drivingKm = route?.distance_m != null ? route.distance_m / 1000 : null
  const showKm = drivingKm ?? straightKm
  const showMi = showKm === null ? null : showKm * KM_TO_MILES
  const fmt = (n) => (n >= 100 ? Math.round(n).toLocaleString() : n.toFixed(1))

  const bounds = route?.geometry?.length ? route.geometry : endpoints

  return (
    <div className="rounded-xl bg-white p-4 shadow">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-bold text-slate-700">Route preview</h2>
        {showKm !== null && (
          <span className="text-xs text-slate-500">
            {drivingKm != null ? 'Driving distance' : 'Straight-line distance'}:{' '}
            {fmt(showMi)} mi ({fmt(showKm)} km)
          </span>
        )}
      </div>
      {straightKm !== null && straightKm > SUSPICIOUS_KM && (
        <div className="mb-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
          These points are {fmt(straightKm * KM_TO_MILES)} miles apart — that doesn't
          look like a commute. One of the addresses probably resolved to the wrong
          place; double-check both locations on the map below.
        </div>
      )}
      <MapContainer
        center={endpoints[0]}
        zoom={12}
        scrollWheelZoom={false}
        className="h-56 w-full rounded-lg"
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {origin && (
          <CircleMarker
            center={[origin.lat, origin.lng]}
            radius={8}
            pathOptions={{ color: '#047857', fillColor: '#10b981', fillOpacity: 0.9 }}
          >
            <LeafletTooltip permanent direction="top">From</LeafletTooltip>
          </CircleMarker>
        )}
        {destination && (
          <CircleMarker
            center={[destination.lat, destination.lng]}
            radius={8}
            pathOptions={{ color: '#b91c1c', fillColor: '#ef4444', fillOpacity: 0.9 }}
          >
            <LeafletTooltip permanent direction="top">To</LeafletTooltip>
          </CircleMarker>
        )}
        {route?.geometry?.length ? (
          <Polyline positions={route.geometry} pathOptions={{ color: '#2563eb', weight: 5, opacity: 0.8 }} />
        ) : (
          endpoints.length === 2 && (
            // Fallback while the route loads or if routing failed.
            <Polyline
              positions={endpoints}
              pathOptions={{ color: '#94a3b8', dashArray: '6 8' }}
            />
          )
        )}
        <FitBounds bounds={bounds} />
      </MapContainer>
      {routeError && (
        <p className="mt-1 text-xs text-amber-600">
          Couldn't draw the road route ({routeError}); showing a straight line.
        </p>
      )}
    </div>
  )
}
