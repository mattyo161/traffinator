import { useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip as LeafletTooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { haversineKm, KM_TO_MILES } from '../utils/geo'

// Beyond this, the points almost certainly aren't a commute (wrong geocode?)
const SUSPICIOUS_KM = 150

function FitBounds({ points }) {
  const map = useMap()
  const key = JSON.stringify(points)
  useEffect(() => {
    if (points.length === 1) {
      map.setView(points[0], 13)
    } else {
      map.fitBounds(L.latLngBounds(points), { padding: [40, 40] })
    }
  }, [key, map]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

export default function RoutePreview({ origin, destination }) {
  const points = [origin, destination].filter(Boolean).map((p) => [p.lat, p.lng])
  if (points.length === 0) return null

  const distanceKm = origin && destination ? haversineKm(origin, destination) : null
  const distanceMi = distanceKm === null ? null : distanceKm * KM_TO_MILES
  const fmt = (n) => (n >= 100 ? Math.round(n).toLocaleString() : n.toFixed(1))

  return (
    <div className="rounded-xl bg-white p-4 shadow">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-bold text-slate-700">Route preview</h2>
        {distanceKm !== null && (
          <span className="text-xs text-slate-500">
            Straight-line distance: {fmt(distanceMi)} mi ({fmt(distanceKm)} km)
          </span>
        )}
      </div>
      {distanceKm !== null && distanceKm > SUSPICIOUS_KM && (
        <div className="mb-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
          These points are {fmt(distanceMi)} miles apart — that doesn't look like a
          commute. One of the addresses probably resolved to the wrong place;
          double-check both locations on the map below.
        </div>
      )}
      <MapContainer
        center={points[0]}
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
        {points.length === 2 && (
          <Polyline positions={points} pathOptions={{ color: '#2563eb', dashArray: '6 8' }} />
        )}
        <FitBounds points={points} />
      </MapContainer>
    </div>
  )
}
