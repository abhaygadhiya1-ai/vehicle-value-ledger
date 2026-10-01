import { useEffect, useState } from 'react'
import { Icon } from './icons'

// Light or dark (after the tool pass, the user): the system's scheme until the viewer picks one with the header's
// toggle; the pick is remembered in this browser. ?theme=light|dark in the address wins, and under ?check a remembered
// pick is ignored, so the look checks run in the theme they ask for. The CSS and the charts follow data-theme.
const KEY = 'vvl-theme'
const root = document.documentElement

export function initTheme() {
  const asked = location.search.match(/[?&]theme=(light|dark)\b/)?.[1]
  let saved: string | null = null
  if (!asked && !/[?&]check\b/.test(location.search)) try { saved = localStorage.getItem(KEY) } catch { /* blocked */ }
  const pick = asked ?? (saved === 'light' || saved === 'dark' ? saved : null)
  if (pick) root.setAttribute('data-theme', pick)
}

export const isDark = () => {
  const a = root.getAttribute('data-theme')
  return a ? a === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
}

export function ThemeToggle() {
  const [dark, setDark] = useState(isDark)
  useEffect(() => {   // follow the attribute and the system, whoever changes them
    const again = () => setDark(isDark())
    const q = matchMedia('(prefers-color-scheme: dark)')
    q.addEventListener('change', again)
    const mo = new MutationObserver(again)
    mo.observe(root, { attributes: true, attributeFilter: ['data-theme'] })
    return () => { q.removeEventListener('change', again); mo.disconnect() }
  }, [])
  const flip = () => {
    const next = isDark() ? 'light' : 'dark'
    const apply = async () => {
      root.setAttribute('data-theme', next)
      try { localStorage.setItem(KEY, next) } catch { /* blocked: the pick lasts until a reload */ }
      // let React and the charts redraw in the new colours before the browser takes the new picture: three frames, or
      // 100 ms where no frames come (a hidden page)
      await new Promise(done => {
        let n = 0
        const frame = () => { if (++n < 3) requestAnimationFrame(frame); else done(null) }
        requestAnimationFrame(frame)
        setTimeout(done, 100)
      })
    }
    // the whole page cross-fades (400 ms, styles.css) where the browser has view transitions; else it switches at once
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches
    // a transition the browser skips (a hidden page, a second click mid-fade) still applies the theme; nothing to report
    if (document.startViewTransition && !still) document.startViewTransition(apply).ready.catch(() => undefined)
    else apply()
  }
  return (
    <button type="button" className="icon-btn theme-btn" role="switch" aria-checked={dark} aria-label="Dark mode"
      title={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={flip}>
      <Icon name={dark ? 'sun' : 'moon'} size={16} />
    </button>
  )
}
