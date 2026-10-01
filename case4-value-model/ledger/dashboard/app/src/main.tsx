import { createRoot } from 'react-dom/client'
import { App } from './App'
import { DASH } from './data'
import './styles.css'
import { initTheme } from './theme'

initTheme()   // before the first paint: the remembered theme, or the one the address asks for

// Charts measure their labels once, on first draw, so both Plex weights load before the first render; otherwise
// ECharts measures a fallback font and Plex's wider text collides.
const fonts = Promise.all(['400 12px "IBM Plex Sans"', '600 12px "IBM Plex Sans"'].map(f => document.fonts.load(f)))
  .catch(() => undefined)

const root = createRoot(document.getElementById('root')!)
fonts.then(() => root.render(DASH ? <App dash={DASH} /> : <p>data.js is missing: run export.py, then reload.</p>))
// the look's numeric checks, only on request (?check): look_check.js beside the page reads it as rendered
if (/[?&]check\b/.test(location.search)) {
  const s = document.createElement('script'); s.src = 'look_check.js'; document.body.appendChild(s)
}
