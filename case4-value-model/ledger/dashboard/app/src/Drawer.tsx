import { createContext, useContext, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import * as Dialog from '@radix-ui/react-dialog'
import type { Dash } from './data'
import { Chart, type ChartOption } from './Chart'
import { axisStyle, base, type Tokens } from './tokens'
import { cap, eur, nf, oneIn, pc } from './format'
import { Badge, Status } from './ui'
import { BodyIcon, Icon, STATUS_EVENT, eventIcon, iconImage } from './icons'
import { asEvent, useActions } from './actions'

// The car drawer: one car's ledger record. Its life as a timeline, one lane per business, above its value and 80% band
// by month; a slider sets what the group knew on a date. Every event carries two dates (when it happened, when the
// group learnt it): an event that had happened but was not yet learnt draws hollow. Actions a person logs on a queue
// join the record as events of the prototype's today, drawn as triangles (simulated, this page only).

export type CarEvent = [happened: string, learnt: string, event: string, source: string, eur: number | null,
  kind: string, detail: string]
export type Car = { make: string; model: string; body: string; registered: string; catalogue: number; buyer: string; contract: string | null
  incentives: number; events: CarEvent[]; marks: [m: string, mark: number, low: number, high: number][]
  ready?: [m: string, p3: number, p12: number][] }

const LANES: { name: string; acc: string; test: (e: CarEvent) => boolean }[] = [
  { name: 'New-car sale', acc: 'var(--acc-oem)', test: e => /^(order|order log|registration|list price|dealer transfer)$/.test(e[2]) },
  { name: 'Incentive claims', acc: 'var(--acc-oem)', test: e => e[2].startsWith('claim') },
  { name: 'Captive finance', acc: 'var(--acc-fin)', test: e => e[3] === 'finance_jv' || /^(timing sent|partner:)/.test(e[2]) },
  { name: 'Keeper register', acc: 'var(--axis)', test: e => /^(first keeper|keeper read|tradein|keeper handover)$/.test(e[2]) },
  { name: 'Used-car business', acc: 'var(--acc-res)', test: e => /^(came to market|resale)$|^(routed|price logged)/.test(e[2]) },
]
const lane = (e: CarEvent) => Math.max(0, LANES.findIndex(l => l.test(e)))
const monthEnd = (m: string) => { const [y, mo] = m.split('-').map(Number); return `${m}-${String(new Date(y, mo, 0).getDate()).padStart(2, '0')}` }

// the record in plain words (the user, 30 September): the store keeps its lineage ids and the Dutch register's own
// values; the page names each source as its source list does ("Each source's date"; the holds' own source is not on it)
// and writes each detail as a person would (anything else passes through)
type Names = Record<string, string>
const sourceName = (s: string, names: Names) => names[s] ?? (s === 'claims controls' ? 'Claims controls' : s)
const eventName = (s: string) => s === 'tradein' ? 'trade-in' : s
function detailText(s: string, car: Car) {
  const kv: Record<string, string> = Object.fromEntries(s.split(/, (?=[a-z ]+: )/).map(p => {
    const [k, ...v] = p.split(': '); return [k, v.join(': ')] }))
  if (kv.make) return `${cap(car.make)} ${car.model}, ${car.body}, ${kv.buyer} buyer`   // the car's own, in English
  if (kv.export) return `${nf(Number(kv['days after registration']), 0)} days after registration, ` +
    (kv.export === 'Ja' ? 'exported' : 'not exported')
  if (kv.dealer) return `dealer ${kv.dealer}, programme ${kv.programme}`
  return kv['first keeper'] || kv['contract type'] || kv.event || s
}

type Ctx = { open: (id: number, from?: HTMLElement | null) => void; has: (id: number) => boolean }
const CarCtx = createContext<Ctx>({ open: () => {}, has: () => false })
export const useCar = () => useContext(CarCtx)

// a car id in a queue: a button that opens its record when the export carries it, plain text otherwise
export function CarButton({ id }: { id: number | null }) {
  const { open, has } = useCar()
  if (id == null) return <span className="muted">unlinked</span>
  return has(id) ? <button type="button" className="car" onClick={e => open(id, e.currentTarget)}
    aria-label={`Car ${id}: open its record`}>{id}</button>
    : <>{id}</>
}

export function CarProvider({ dash, t, children }: { dash: Dash; t: Tokens; children: ReactNode }) {
  const cars = dash.proto.cars as Record<string, Car>
  const names = useMemo<Names>(() => Object.fromEntries(dash.proto.sources.map(s => [s.source, s.name])), [dash])
  const [id, setId] = useState<number | null>(null)
  const opener = useRef<HTMLElement | null>(null)   // focus returns here when the drawer closes
  // A queue row grows into the car's record and shrinks back into it (after the tool pass, part 9): the row and the
  // drawer share one view transition name, so the browser morphs one into the other (300 ms, styles.css) while the rest
  // of the page cross-fades. Opened any other way, or without view transitions, or under reduced motion: as before.
  const [morph, setMorph] = useState(false)
  const row = useRef<HTMLElement | null>(null)
  const morphs = () => !!document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches
  const shift = (update: () => void, done?: () => void) => {
    const root = document.documentElement
    root.dataset.vt = 'car'
    const vt = document.startViewTransition(update)
    vt.ready.catch(() => undefined)   // skipped (a hidden page, a second click): the update still ran
    vt.finished.finally(() => { delete root.dataset.vt; done?.() })
  }
  const ctx = useMemo<Ctx>(() => ({
    open: (x: number, from?: HTMLElement | null) => {
      opener.current = document.activeElement as HTMLElement
      const tr = from?.closest('tr') as HTMLElement | null
      if (!tr || !morphs()) { setMorph(false); setId(x); return }
      row.current = tr
      tr.style.viewTransitionName = 'car-record'
      shift(() => { tr.style.viewTransitionName = ''; flushSync(() => { setMorph(true); setId(x) }) })
    },
    has: (x: number) => String(x) in cars }), [cars])
  const close = () => {
    const tr = row.current
    if (!morph || !tr?.isConnected || !morphs()) { setId(null); setMorph(false); return }
    shift(() => { flushSync(() => setId(null)); tr.style.viewTransitionName = 'car-record' },
      () => { tr.style.viewTransitionName = ''; setMorph(false) })
  }
  const car = id == null ? null : cars[String(id)]
  if (/[?&]check\b/.test(location.search)) (window as unknown as { LEDGER: Ctx }).LEDGER = ctx
  return (
    <CarCtx.Provider value={ctx}>
      {children}
      <Dialog.Root open={car != null} onOpenChange={o => { if (!o) close() }}>
        <Dialog.Portal>
          <Dialog.Overlay className="scrim" data-morph={morph || undefined} />
          <Dialog.Content className="drawer" aria-describedby={undefined} data-morph={morph || undefined}
            onCloseAutoFocus={e => { e.preventDefault(); if (opener.current?.isConnected) opener.current.focus() }}>
            {car && <Record id={id!} car={car} t={t} names={names} />}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </CarCtx.Provider>
  )
}

function Record({ id, car: car0, t, names }: { id: number; car: Car; t: Tokens; names: Names }) {
  const { acts, today } = useActions()
  const car = useMemo(() => ({ ...car0, events: [...car0.events,
    ...acts.filter(a => a.car === id).map(a => asEvent(a, today))].sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0) }),
  [car0, acts, id, today])
  const dates = useMemo(() => [...new Set([...car.events.map(e => e[1]), ...car.marks.map(m => monthEnd(m[0]))])].sort(), [car])
  const [i, setI] = useState(dates.length - 1)
  const asof = dates[i]
  const ev = car.events.filter(e => e[0] <= asof)
  const mk = car.marks.filter(m => m[0] <= asof.slice(0, 7))
  const rd = (car.ready ?? []).filter(r => r[0] <= asof.slice(0, 7)).pop()
  const first = [...car.events.map(e => e[0]), ...car.marks.map(m => m[0] + '-01')].sort()[0]
  const last = [...car.events.map(e => e[0]), ...car.marks.map(m => monthEnd(m[0]))].sort().pop()!

  const option = useMemo<ChartOption>(() => {
    // 3% of the span either side, so an icon on the first or last day stays clear of the lane names and the edge
    const t0 = Date.parse(first), t1 = Date.parse(last), pad = 0.03 * (t1 - t0)
    const x = (g: number) => ({ type: 'time', gridIndex: g, min: t0 - pad, max: t1 + pad, ...axisStyle(t),
      axisLabel: { ...axisStyle(t).axisLabel, show: g === 1, hideOverlap: true }, splitLine: { show: g === 1, lineStyle: { color: t.grid } } })
    const asofLine = { silent: true, symbol: 'none', animation: false, lineStyle: { color: t.ink, width: 1, type: [4, 3] },
      label: { show: false }, data: [{ xAxis: asof }] }
    return {
      ...base(t),
      tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { seriesIndex: number; dataIndex: number; value: unknown }) => {
        if (p.seriesIndex === 0) {
          const e = ev[p.dataIndex]
          return `<b>${eventName(e[2])}</b> (${sourceName(e[3], names)})<br>happened ${e[0]}, learnt ${e[1] > asof ? 'not yet' : e[1]}` +
            (e[4] == null ? '' : `<br>${eur(e[4], 2)}`) + (e[6] ? `<br>${detailText(e[6], car)}` : '') + (e[5] === 'synthetic' ? '<br>synthetic'
              : e[5] === 'simulated' ? '<br>logged on this page (simulated)' : '')
        }
        const m = mk[p.dataIndex]
        return m ? `${m[0]}<br><b>${eur(m[1])}</b> (80% band ${eur(m[2])}–${eur(m[3])})` : ''
      } },
      grid: [{ left: 128, right: 16, top: 8, height: 118 }, { left: 128, right: 16, top: 148, bottom: 24 }],
      xAxis: [x(0), x(1)],
      yAxis: [
        { type: 'category', gridIndex: 0, inverse: true, data: LANES.map(l => l.name), ...axisStyle(t),
          axisLine: { show: false }, axisLabel: { ...axisStyle(t).axisLabel, color: t.ink }, splitLine: { show: true, lineStyle: { color: t.grid } } },
        { type: 'value', gridIndex: 1, ...axisStyle(t), axisLine: { show: false }, scale: true,
          axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => '€' + nf(v / 1000, 0) + 'k' } },
      ],
      series: [
        { type: 'scatter', xAxisIndex: 0, yAxisIndex: 0,
          // each event type's icon (the tool pass, part 7); a claim held or in review keeps the status shapes
          data: ev.map(e => {
            const known = e[1] <= asof, node = eventIcon(e[2])
            if (STATUS_EVENT.test(e[2])) {
              const hold = /hold/.test(e[2])
              return { value: [e[0], lane(e)], symbol: hold ? 'rect' : 'triangle', symbolSize: 12,
                itemStyle: known ? { color: hold ? t.crit : t.warn, borderColor: t.surface, borderWidth: 1 }
                  : { color: 'transparent', borderColor: t.ink2, borderWidth: 1.5 } }
            }
            if (!node) return { value: [e[0], lane(e)], symbol: 'circle', symbolSize: 10,    // a type with no icon yet
              itemStyle: known ? { color: t.series } : { color: 'transparent', borderColor: t.axis, borderWidth: 1.5 } }
            return { value: [e[0], lane(e)], symbolSize: 20,
              symbol: iconImage(node, known ? t.series : t.axis, known ? t.area : t.surface, known ? t.surface : t.axis,
                e[5] === 'simulated') }
          }),
          markLine: asofLine },
        { type: 'line', xAxisIndex: 1, yAxisIndex: 1, stack: 'band', silent: true, symbol: 'none', lineStyle: { opacity: 0 },
          data: mk.map(m => [monthEnd(m[0]), m[2]]), tooltip: { show: false } },
        { type: 'line', xAxisIndex: 1, yAxisIndex: 1, stack: 'band', silent: true, symbol: 'none', lineStyle: { opacity: 0 },
          areaStyle: { color: t.area }, data: mk.map(m => [monthEnd(m[0]), m[3] - m[2]]), tooltip: { show: false } },
        { type: 'line', xAxisIndex: 1, yAxisIndex: 1, showSymbol: false, color: t.series, lineStyle: { width: 2 },
          data: mk.map(m => [monthEnd(m[0]), m[1]]), markLine: asofLine },
      ],
    }
  }, [ev, mk, asof, first, last, t, names])

  const known = car.events.filter(e => e[1] <= asof).length
  return (
    <>
      <header className="dr-head">
        <div>
          <Dialog.Title className="dr-title"><BodyIcon body={car.body} size={40} /> Car {id}, {cap(car.make)} {car.model}</Dialog.Title>
          <p className="dr-facts">{cap(car.body)}, registered {car.registered}, catalogue {eur(car.catalogue)}, {car.buyer}
            {car.contract ? `, ${car.contract}` : ''}, incentives paid {eur(car.incentives)} <Badge layer="proto" short /></p>
        </div>
        <Dialog.Close className="icon-btn" aria-label="Close the car's record">
          <Icon name="close" size={16} />
        </Dialog.Close>
      </header>
      <div className="dr-asof">
        <label htmlFor="asofr">What the group knew on</label>
        <input id="asofr" type="range" min={0} max={dates.length - 1} value={i} onChange={e => setI(Number(e.target.value))}
          style={{ '--p': dates.length > 1 ? i / (dates.length - 1) : 1 } as CSSProperties} aria-valuetext={asof} />
        <output htmlFor="asofr">{asof}</output>
      </div>
      <p className="dr-ready">{rd ? <>Chance of coming to market within 3 months at {rd[0]}: <b>{pc(rd[1])}</b> ({oneIn(rd[1])});
        within 12 months: {pc(rd[2])}.</> : 'Not yet scored on this date (scores start at age one).'}{' '}
        {nf(known)} of {nf(car.events.length)} events known.</p>
      <div className="chart dr-chart">
        <Chart option={option} height={330} label={`Car ${id}: ${nf(ev.length)} events to ${asof} in five lanes, and its ` +
          `value by month${mk.length ? `, ${eur(mk[mk.length - 1][1])} at ${mk[mk.length - 1][0]}` : ''}`} />
        <ul className="nl-key dr-key">
          <li><i className="k-dot" />an event's icon, known by the date</li><li><i className="k-dot hollow" />happened, not yet learnt</li>
          <li><i className="k-sq" />claim held</li><li><i className="k-tri" />claim in review</li>
          <li><i className="k-band" />value and its 80% band</li>
          {car.events.some(e => e[5] === 'simulated') && <li><i className="k-dot dashed" />logged on this page (simulated)</li>}
        </ul>
      </div>
      <details className="dr-events">
        <summary>All {nf(ev.length)} events to {asof}</summary>
        <div className="twin tall">
          <table>
            <thead><tr><th>Happened</th><th>Learnt</th><th>Event</th><th>Source</th><th className="n">€</th><th>Detail</th></tr></thead>
            <tbody>{ev.map((e, j) => <tr key={j} className={e[1] > asof ? 'unknown' : ''}><td className="nowrap">{e[0]}</td>
              <td className="nowrap">{e[1] > asof ? 'not yet' : e[1]}</td><td><EventName e={e} /></td>
              <td>{sourceName(e[3], names)}</td><td className="n">{e[4] == null ? '' : eur(e[4], 2)}</td>
              <td>{e[6] && detailText(e[6], car)}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
      <p className="dr-note">Real: the car, its registration, keeper changes and value. Synthetic: claims, contracts,
        decisions and resale prices. Icons: IBM's Carbon Design System, Apache License 2.0 (LICENSE-carbon.txt beside this page).
        Body-type icons: Material Design Icons by Pictogrammers, Apache 2.0 (LICENSE-mdi.txt).</p>
    </>
  )
}

// an event's name on the record, after its icon; a claim held or in review shows as a status (a square, a triangle)
function EventName({ e }: { e: CarEvent }) {
  const tail = e[5] === 'synthetic' ? ' (synthetic)' : e[5] === 'simulated' ? ' (simulated)' : ''
  if (STATUS_EVENT.test(e[2])) return <Status kind={/hold/.test(e[2]) ? 'crit' : 'warn'}>{e[2]}{tail}</Status>
  const node = eventIcon(e[2])
  return <span className="ev-name">{node && <Icon name={node} />}{eventName(e[2])}{tail}</span>
}
