// Runs index.html?check in headless Chrome, cache off, and prints the result and any console errors. The page is served
// at 127.0.0.1:8765 (.claude/launch.json's "dashboard"). Headless Chrome draws every frame; a browser pane that is not on
// screen does not, and slows its timers, so motion never ends there (after the tool pass, part 4).
// usage: node look_run.mjs <width> <height> <light|dark> [shot.png] [js to run instead of the check]
import { spawn } from 'node:child_process'
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs'
const [W, H, theme, shot, probe] = process.argv.slice(2)
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const dir = mkdtempSync(process.env.TMPDIR + '/lookchrome-')
const port = 9300 + Math.floor(Math.random() * 500)
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`,
  '--no-first-run', `--window-size=${W},${H}`, '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' })
const sleep = ms => new Promise(r => setTimeout(r, ms))
let ws
for (let i = 0; i < 50 && !ws; i++) {
  try {
    const t = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(x => x.type === 'page')
    ws = new WebSocket(t.webSocketDebuggerUrl)
  } catch { await sleep(200) }
}
await new Promise(r => ws.addEventListener('open', r))
let id = 0; const wait = new Map(), errors = []
ws.addEventListener('message', e => {
  const m = JSON.parse(e.data)
  if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text)
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map(a => a.value ?? a.description).join(' '))
})
const cdp = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })) })
const evaluate = async expr => (await cdp('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value
await cdp('Runtime.enable'); await cdp('Network.enable'); await cdp('Network.setCacheDisabled', { cacheDisabled: true })
await cdp('Emulation.setDeviceMetricsOverride', { width: +W, height: +H, deviceScaleFactor: 1, mobile: +W < 768 })
// MEDIA="prefers-reduced-transparency:reduce" (comma-separated) emulates the system's settings, for the glass's fallbacks
if (process.env.MEDIA) await cdp('Emulation.setEmulatedMedia', { features: process.env.MEDIA.split(',').map(f => { const [name, value] = f.split(':'); return { name, value } }) })
const url = `http://127.0.0.1:8765/index.html?${probe ? '' : 'check&'}theme=${theme}`
await cdp('Page.navigate', { url })
let out
if (probe) { await sleep(2500); out = await evaluate(`(async () => { ${probe} })()`) }
else for (let i = 0; i < 180 && !out; i++) { await sleep(1000); out = await evaluate(`window.LOOK && JSON.stringify({ h: document.querySelector('#lookcheck h2').textContent, fails: LOOK.filter(o => o.pass === 'FAIL'), motion: LOOK.filter(o => /^(Motion|Theme|Charts draw|Numbers roll|Queue rows glide|A row opens)/.test(o.check)).map(o => o.pass + ': ' + o.detail) })`) }
// HOLD="<selector>" presses the mouse on that element's centre and drags 24 px right, held for the screenshot;
// CLIP="x,y,width,height,scale" crops and enlarges it (the sliders' glass knob, Liquid Glass part 3)
if (process.env.HOLD) {
  const [x, y] = await evaluate(`(() => { const b = document.querySelector(${JSON.stringify(process.env.HOLD)}).getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2] })()`)
  await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 })
  await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x + 24, y, button: 'left', buttons: 1 })
  await sleep(400)
}
const clip = process.env.CLIP && (([x, y, width, height, scale]) => ({ x, y, width, height, scale }))(process.env.CLIP.split(',').map(Number))
if (shot) { const s = await cdp('Page.captureScreenshot', { format: 'png', ...(clip ? { clip } : {}) }); writeFileSync(shot, Buffer.from(s.result.data, 'base64')) }
console.log(typeof out === 'string' ? out : JSON.stringify(out))
console.log('console errors:', errors.length ? errors.join(' | ') : 'none')
ws.close(); proc.kill()
// the throwaway profile (about 60 MB a run) goes with the browser
proc.on('exit', () => rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }))   // Chrome can still be writing
