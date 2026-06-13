// One color per day of week (Mon..Sun). The Okabe-Ito palette is a widely
// used colorblind-safe set; High contrast maximizes separation on white.
export const PALETTES = {
  default: {
    label: 'Default',
    colors: ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#64748b'],
  },
  okabeIto: {
    label: 'Colorblind-safe (Okabe-Ito)',
    colors: ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#D55E00', '#56B4E9', '#000000'],
  },
  highContrast: {
    label: 'High contrast',
    colors: ['#0000CC', '#CC0000', '#006600', '#CC00CC', '#FF8C00', '#008B8B', '#000000'],
  },
}

export function hexToRgba(hex, alpha) {
  const v = hex.replace('#', '')
  const r = parseInt(v.slice(0, 2), 16)
  const g = parseInt(v.slice(2, 4), 16)
  const b = parseInt(v.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
