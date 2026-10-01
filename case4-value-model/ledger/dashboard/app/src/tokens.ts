import { useEffect, useState } from 'react'

// Charts read their colours from the CSS tokens (styles.css), so light and dark stay one definition. The hook re-reads
// them when the system scheme or the page's data-theme changes.
const NAMES = ['ink', 'ink2', 'muted', 'line', 'grid', 'axis', 'surface', 'overlay', 'series', 'deemph', 'area',
  'ord1', 'ord2', 'crit', 'warn', 'good'] as const
export type Tokens = Record<(typeof NAMES)[number], string> & { reduced: boolean }

function read(): Tokens {
  const s = getComputedStyle(document.documentElement)
  const t = Object.fromEntries(NAMES.map(n => [n, s.getPropertyValue('--' + n).trim()])) as unknown as Tokens
  t.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  return t
}

export function useTokens(): Tokens {
  const [t, setT] = useState(read)
  useEffect(() => {
    const again = () => setT(read())
    const queries = ['(prefers-color-scheme: dark)', '(prefers-reduced-motion: reduce)'].map(q => matchMedia(q))
    queries.forEach(q => q.addEventListener('change', again))
    const mo = new MutationObserver(again)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => { queries.forEach(q => q.removeEventListener('change', again)); mo.disconnect() }
  }, [])
  return t
}

// Phone width: a chart whose labels need fixed room (the flow) lays out differently below 720 px.
export function useNarrow(): boolean {
  const q = '(max-width: 720px)'
  const [n, setN] = useState(() => matchMedia(q).matches)
  useEffect(() => {
    const m = matchMedia(q), on = () => setN(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return n
}

// What every chart shares: Plex at 12 px in the text tokens, recessive axes, and a tooltip on the overlay surface. Motion
// (after the tool pass, part 5): a chart draws in over 600 ms when its view opens, its points 12 ms apart (at most
// 240 ms); a change of data (the slider, a toggle) moves over 400 ms; none under reduced motion.
export function base(t: Tokens) {
  return {
    aria: { enabled: true },
    textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 12, color: t.ink2 },
    animation: !t.reduced,
    animationDuration: 600,
    animationEasing: 'cubicOut' as const,
    animationDelay: (i: number) => Math.min(i, 20) * 12,
    animationDurationUpdate: 400,
    animationEasingUpdate: 'cubicOut' as const,
    tooltip: {
      backgroundColor: t.overlay, borderColor: t.line, borderWidth: 1, padding: [8, 12],
      textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 12, color: t.ink },
      extraCssText: 'box-shadow: var(--elev-overlay); border-radius: 8px;',
    },
  }
}

export const axisStyle = (t: Tokens) => ({
  axisLine: { lineStyle: { color: t.axis } },
  axisTick: { show: false },
  axisLabel: { color: t.ink2, fontFamily: 'IBM Plex Sans', fontSize: 12 },
  splitLine: { lineStyle: { color: t.grid } },
})
