// The deck appendix's screenshots (the user, 30 September): each view whole in one image, in light, at 1,440 px wide
// and twice the pixels, then one car's record. The window is made as tall as the page (or the record), so nothing is
// cut and nothing scrolls; at 1,440 px no view is taller than about 1.6 screens, so no image is phone-shaped. The page
// is served at 127.0.0.1:8765 (.claude/launch.json's "dashboard"). Retake after any change to the dashboard.
// usage: node deck_shots.mjs <folder>
import { spawn } from 'node:child_process'
import { writeFileSync, mkdtempSync, mkdirSync, rmSync } from 'node:fs'
const out = process.argv[2]
if (!out) { console.log('usage: node deck_shots.mjs <folder>'); process.exit(1) }
mkdirSync(out, { recursive: true })
const W = 1440, H = 900, CAR = 55089   // the showcase car the look checks open
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
})
const cdp = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })) })
const evaluate = async expr => (await cdp('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value
const metrics = (h, scale = 1) => cdp('Emulation.setDeviceMetricsOverride', { width: W, height: h, deviceScaleFactor: scale, mobile: false })
// tiles and cards arrive, numbers roll, charts draw in: let them start, then end them where they rest
const settle = async () => { await sleep(1500); await evaluate('document.getAnimations().forEach(a => a.finish())'); await sleep(300) }
const view = i => evaluate(`(() => { const el = [...document.querySelectorAll('[role=tab]'), document.querySelector('.office-btn')][${i}];
  el.getAttribute('role') === 'tab' ? el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })) : el.click();
  scrollTo(0, 0) })()`)
// the window grown to the height asked (the page's or the record's), measured again once grown, then captured
const shoot = async (file, measure) => {
  let h = await evaluate(measure)
  for (let k = 0; k < 3; k++) { await metrics(h, 2); await settle(); const h2 = await evaluate(measure); if (h2 === h) break; h = h2 }
  const s = await cdp('Page.captureScreenshot', { format: 'png' })
  writeFileSync(`${out}/${file}`, Buffer.from(s.result.data, 'base64'))
  console.log(`${file}: ${W} × ${h} px (${(W / h).toFixed(2)} wide to 1 high), saved at twice the pixels`)
  await metrics(H)
}

await cdp('Runtime.enable'); await cdp('Network.enable'); await cdp('Network.setCacheDisabled', { cacheDisabled: true })
await metrics(H)
await cdp('Page.navigate', { url: 'http://127.0.0.1:8765/index.html?theme=light' })
await sleep(2500)
const VIEWS = ['1_management', '2_new_car_incentives', '3_captive_finance', '4_used_car_resale', '5_programme_office']
for (const [i, file] of VIEWS.entries()) {
  await view(i); await settle()
  await shoot(`${file}.png`, 'document.documentElement.scrollHeight')
}
// one car's record, opened from the search as a person would, over the resale view
await view(3); await settle()
await evaluate(`(() => { const i = document.querySelector('.search input');
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, '${CAR}');
  i.dispatchEvent(new Event('input', { bubbles: true })) })()`)
await sleep(500)
await evaluate(`document.querySelector('[aria-label^="Car ${CAR},"]').click()`)
await settle()
// its events listed, not folded, and every one shown: the image only, the table's scroll box lifted (the page keeps it)
await evaluate(`document.querySelectorAll('.drawer details').forEach(d => d.open = true);
  document.querySelectorAll('.drawer .twin').forEach(t => { t.style.maxHeight = 'none'; t.style.overflow = 'visible' })`)
await shoot(`6_car_record_${CAR}.png`, `Math.max(${H}, document.querySelector('.drawer').scrollHeight)`)
console.log('page errors:', errors.length ? errors.join(' | ') : 'none')
ws.close(); proc.kill()
proc.on('exit', () => rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }))
