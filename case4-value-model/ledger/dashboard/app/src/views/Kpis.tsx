import type { ReactNode } from 'react'
import type { Group, Proto } from '../data'
import { nf, pc } from '../format'
import { Badge, Status, type Twin } from '../ui'

// KPIs as Few's bullet graphs (Bullet Graph Design Specification, rev. 2013): the reading as a heavy bar, the target
// as a perpendicular tick, two ranges as shades of one neutral (off target darker). A pace or reach target is read
// only beside the guard that stops it being gamed. No bar where the prototype can make no reading: the phase that
// will read it instead.

type Kpi = {
  name: string
  target: string
  reading?: number
  unit?: '%'
  // the target as a range on the scale: [lo, hi]; a reading inside it is on target
  ok?: [number, number]
  max?: number          // the scale's end (it starts at zero)
  whose?: ReactNode     // what the reading measures
  later?: string        // the phase that reads it, when there is no reading
  now?: string          // a single's reading in words, when the page has one (pricing alignment, from logged proposals)
  pending?: string      // a reading the design exists for but the data can't give yet (the pilot's uplift)
}
type Align = { inside: number; outside: number; thin: number }

export function kpis(g: Group, p: Proto, al?: Align) {
  const k = g.kpis_targets, c = p.claims, pl = p.upgrade.pilot
  const pairs: [Kpi, Kpi][] = [
    [{ name: 'Days to settle a claim', target: `≤ ${nf(k.claim_days)} working days`, later: 'read from Phase 1' },
     { name: 'Claims recoveries certified in the pilot', target: `≥ €${k.claims_recovered}m a year`,
       later: 'read in Phase 2' }],
    [{ name: 'Claims sent to human review', target: `≤ ${pc(k.review_rate, 0)}`, reading: c.review_share, unit: '%',
       ok: [0, k.review_rate], max: 2 * k.review_rate, whose: <Badge layer="proto" short /> },
     { name: 'Real duplicates flagged', target: `≥ ${pc(k.recall, 0)}`, reading: c.tool_recall, unit: '%',
       ok: [k.recall, 100], max: 100, whose: <span className="whose">our tool, synthetic</span> }],
    [{ name: 'Incentive spend linked to a VIN', target: `≥ ${pc(k.vin_link, 0)} of value`, reading: c.linked_share_value,
       unit: '%', ok: [k.vin_link, 100], max: 100, whose: <Badge layer="proto" short /> },
     { name: 'Duplicate flags that are real', target: `≥ ${pc(k.precision, 0)}`, reading: c.tool_precision, unit: '%',
       ok: [k.precision, 100], max: 100, whose: <span className="whose">our tool, synthetic</span> }],
    [{ name: 'Days cut from the time to sale', target: `≥ ${nf(k.days_cut)} days`,
       later: 'read in Phase 3' },
     { name: "Routed cars' margin after all costs", target: `≥ ${pc(k.route_margin, 0)}`, later: 'read in Phase 3' }],
    [{ name: "The engine's 80% band covers returns", target: `80% ± ${nf(k.band_tol)} points`,
       reading: k.band_cov_heldout, unit: '%', ok: [80 - k.band_tol, 80 + k.band_tol], max: 100,
       whose: <><span className="whose">held-out adverts</span> <Badge layer="group" short /></> },
     { name: 'The engine against the bought guide', target: `no worse by > ${nf(k.engine_margin)} point`,
       later: 'read in Phase 3' }],
  ]
  // one short line a single (the text diet, the user, 30 September): the pilot's design and size are in the card's ⓘ
  const singles: Kpi[] = [
    { name: 'Retention uplift over a randomised control', target: `≥ ${nf(k.uplift)} points`,
      pending: 'not yet measured',
      later: `not yet measured: ${nf(pl.treated)} treated, ${nf(pl.control)} held out` },
    { name: 'Ledger against the general ledger', target: `within ±${pc(k.gl, 1)}`, later: 'monthly from Phase 2' },
    { name: 'Market drift unseen between re-marks', target: `≤ ${pc(k.drift, 1)}`, later: 'monthly re-mark' },
    { name: 'Override payoff', target: 'deliberately no target', later: 'from Phase 2' },
    { name: "Pricers' proposals inside the tied band", target: 'a reading, no target',
      later: 'from logged proposals',
      now: al && al.inside + al.outside > 0 ? `${nf(al.inside)} of ${nf(al.inside + al.outside)} logged, ` +
        `${pc(100 * al.inside / (al.inside + al.outside), 0)}` + (al.thin ? `; ${nf(al.thin)} with little history, signed off apart` : '')
        : undefined },
  ]
  return { pairs, singles }
}

const onTarget = (x: Kpi) => x.reading != null && x.ok != null && x.reading >= x.ok[0] && x.reading <= x.ok[1]

export function kpiSummary(pairs: [Kpi, Kpi][]) {
  const read = pairs.flat().filter(x => x.reading != null)
  return { read, on: read.filter(onTarget), off: read.filter(x => !onTarget(x)) }
}

function Bullet({ x }: { x: Kpi }) {
  const max = x.max!, [lo, hi] = x.ok!, w = (v: number) => `${Math.min(100, 100 * v / max)}%`
  const good = onTarget(x)
  return (
    <div className="bullet" aria-hidden="true">
      <span className="rng off" />
      <span className="rng on" style={{ left: w(lo), width: `calc(${w(hi)} - ${w(lo)})` }} />
      <span className={'bar' + (good ? '' : ' miss')} style={{ width: w(x.reading!) }} />
      {lo > 0 && <span className="tick" style={{ left: w(lo) }} />}
      {hi < max && <span className="tick" style={{ left: w(hi) }} />}
    </div>
  )
}

function Row({ x }: { x: Kpi }) {
  const has = x.reading != null
  return (
    <div className="kpi">
      <div className="kpi-name">{x.name}<span className="kpi-target">{x.target}</span></div>
      {has ? <Bullet x={x} /> : <div className="bullet empty" aria-hidden="true" />}
      <div className="kpi-read">
        {has ? <><b>{pc(x.reading, 1)}</b> {x.whose} {onTarget(x) ? <Status kind="ok">on target</Status>
          : <Status kind="crit">below target</Status>}</>
          : <span className="later">{x.later}</span>}
      </div>
    </div>
  )
}

export function KpiBoard({ g, p, al }: { g: Group; p: Proto; al?: Align }) {
  const { pairs, singles } = kpis(g, p, al)
  return (
    <div className="chart kpis" role="group" aria-label="KPIs beside their guards; the table view lists each reading">
      <div className="kpi-cols"><span>Pace or reach</span><span>Its guard</span></div>
      {pairs.map(([a, b], i) => <div className="kpi-pair" key={i}><Row x={a} /><Row x={b} /></div>)}
      <div className="kpi-singles">
        {singles.map(s => <span key={s.name} className="single"><b>{s.name}</b> {s.target}; {s.now
          ? <b>{s.now}</b> : <span className="later">{s.later}</span>}</span>)}
      </div>
    </div>
  )
}

export function kpiTwin(g: Group, p: Proto, al?: Align): Twin {
  const { pairs, singles } = kpis(g, p, al)
  const row = (x: Kpi, role: string) => [x.name, role, x.target, x.reading != null ? pc(x.reading, 1) : x.pending ?? '',
    x.reading != null ? (onTarget(x) ? 'on target' : 'below target') : x.later ?? '']
  return {
    cols: ['KPI', 'Role', 'Target', 'Reading', 'Status or when read'],
    rows: [...pairs.flatMap(([a, b]) => [row(a, 'pace or reach'), row(b, 'its guard')]),
      ...singles.map(s => s.now ? [s.name, 'single', s.target, s.now, 'logged on this page (simulated)'] : row(s, 'single'))],
    num: [false, false, false, true, false],
  }
}
