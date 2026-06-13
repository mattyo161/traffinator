import { useMemo, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { PALETTES, hexToRgba } from '../palettes'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

const toMinutes = (s) => (s == null ? null : Math.round((s / 60) * 10) / 10)

export default function CommuteChart({ results, paletteKey, highlightDay, onHighlightDay }) {
  // highlightDay (from parent) is the pinned day; hoverDay previews on legend hover.
  const [hoverDay, setHoverDay] = useState(null)
  const activeDay = hoverDay ?? highlightDay

  const palette = PALETTES[paletteKey]?.colors ?? PALETTES.default.colors

  const data = useMemo(() => {
    const datasets = []
    for (const dayResult of results.results) {
      const color = palette[dayResult.day % palette.length]
      const dimmed = activeDay !== null && activeDay !== dayResult.day
      const minutes = {
        min: dayResult.points.map((p) => toMinutes(p.min_s)),
        typical: dayResult.points.map((p) => toMinutes(p.typical_s)),
        max: dayResult.points.map((p) => toMinutes(p.max_s)),
      }
      const bandAlpha = dimmed ? 0.04 : activeDay === dayResult.day ? 0.28 : 0.14
      // Invisible upper band edge (max); the next dataset fills down to it.
      datasets.push({
        label: `${dayResult.day_name} max`,
        data: minutes.max,
        borderWidth: 0,
        pointRadius: 0,
        pointHitRadius: 0,
        fill: false,
        role: 'band',
        day: dayResult.day,
      })
      // Lower band edge (min), shaded up to the max dataset above it.
      datasets.push({
        label: `${dayResult.day_name} min`,
        data: minutes.min,
        borderWidth: 0,
        pointRadius: 0,
        pointHitRadius: 0,
        fill: '-1',
        backgroundColor: hexToRgba(color, bandAlpha),
        role: 'band',
        day: dayResult.day,
      })
      // Typical (best guess) line — the only dataset shown in the legend.
      datasets.push({
        label: dayResult.day_name,
        data: minutes.typical,
        borderColor: hexToRgba(color, dimmed ? 0.15 : 1),
        backgroundColor: hexToRgba(color, dimmed ? 0.15 : 1),
        borderWidth: activeDay === dayResult.day ? 3.5 : 2,
        pointRadius: 2.5,
        pointHoverRadius: 5,
        tension: 0.3,
        spanGaps: false,
        fill: false,
        role: 'typical',
        day: dayResult.day,
        bandMin: minutes.min,
        bandMax: minutes.max,
      })
    }
    return { labels: results.labels, datasets }
  }, [results, palette, activeDay])

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { title: { display: true, text: 'Time of day' } },
        y: {
          title: { display: true, text: 'Duration (minutes)' },
          beginAtZero: false,
        },
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            usePointStyle: true,
            generateLabels(chart) {
              return chart.data.datasets
                .map((ds, i) => ({ ds, i }))
                .filter(({ ds }) => ds.role === 'typical')
                .map(({ ds, i }) => ({
                  text: ds.label + (highlightDay === ds.day ? ' ◉' : ''),
                  fillStyle: ds.borderColor,
                  strokeStyle: ds.borderColor,
                  fontColor: '#334155',
                  pointStyle: 'line',
                  lineWidth: 3,
                  datasetIndex: i,
                }))
            },
          },
          onClick(e, item, legend) {
            const day = legend.chart.data.datasets[item.datasetIndex].day
            onHighlightDay(highlightDay === day ? null : day)
            setHoverDay(null)
          },
          onHover(e, item, legend) {
            const day = legend.chart.data.datasets[item.datasetIndex].day
            setHoverDay(day)
            e.native.target.style.cursor = 'pointer'
          },
          onLeave(e) {
            setHoverDay(null)
            e.native.target.style.cursor = 'default'
          },
        },
        tooltip: {
          filter: (item) => item.dataset.role === 'typical',
          callbacks: {
            label(ctx) {
              const ds = ctx.dataset
              const idx = ctx.dataIndex
              const typical = ctx.parsed.y
              if (typical == null) return `${ds.label}: no data`
              const min = ds.bandMin[idx]
              const max = ds.bandMax[idx]
              return `${ds.label}: ${typical} min (range ${min}–${max} min)`
            },
          },
        },
      },
    }),
    [highlightDay, onHighlightDay]
  )

  return (
    <div className="relative h-[60vh] min-h-[400px] w-full lg:h-full">
      <Line data={data} options={options} />
    </div>
  )
}
