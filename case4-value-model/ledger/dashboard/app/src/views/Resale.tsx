import { useEffect, useMemo, useRef, useState } from 'react'
import type { Dash, DeskRow, SupplyRow } from '../data'
import { Chart, type ChartApi, type ChartOption } from '../Chart'
import { axisStyle, base, type Tokens } from '../tokens'
import { cap, eur, eurMraw, monthName, nf, pc } from '../format'
import { Band, Card, ChanceCell, ModelCell, Queue, Status, Tile, TypeChip, ValueCell, scaleOf, typeList, type Banded, type Col } from '../ui'
import type { ViewId } from '../views'
import { CarButton } from '../Drawer'
import { useActions } from '../actions'

// The used-car business (leak 3, the value nobody recovers), opening on the desk's day: the two work lists (incoming
// stock to prepare, cars back to price inside the tied band, each with the in-house margin it still has at least);
// what arrives, by model and month; and where the engine's history is too thin to price without a person.

type Props = { dash: Dash; t: Tokens; open: (v: ViewId) => void }
type Model = { make: string; model: string }
const same = (a: Model, b: Model | null) => b != null && a.make === b.make && a.model === b.model

export function Resale({ dash, t }: Props) {
  const P = dash.proto
  const [model, setModel] = useState<Model | null>(null)
  const tot = Object.fromEntries(P.supply_totals.map(s => [s.book, s]))
  return (
    <>
      <Band compact title="Used-car resale" role="the pricing and remarketing desk" info={{
        serves: 'the used-car business (leak 3: the value nobody recovers). The queue shows what is about to arrive, ' +
          'so stock, reconditioning and pricing are ready before the cars are. Decides the retail price inside the ' +
          'tied band; the channel, country and timing of each sale; sign-off on little-history cars.' }}>
        <Tile v={nf(P.desk_count)} l="Back this quarter, to price" />
        <Tile v={nf(P.desk_past_breakeven)} l="Past the channel break-even"
          note={`back over ${nf(dash.group.prices.channel_breakeven_days)} days`}
          status={P.desk_past_breakeven === 0 ? <Status kind="ok">none</Status> : <Status kind="warn">check the trade</Status>} />
        <Tile v={nf(tot.fleet.expected_3m + tot.retail.expected_3m)} l="Due in the next three months"
          note={eurMraw(tot.fleet.expected_eur + tot.retail.expected_eur)} />
        <Tile v={`${nf(P.thin.models)} of ${nf(P.thin.of_models)}`} l="Models with too little history" />
      </Band>
      <div className="wrap grid">
        <WorkCard dash={dash} model={model} setModel={setModel} />
        <ModelsCard dash={dash} t={t} model={model} setModel={setModel} />
        <MonthsCard dash={dash} t={t} />
        <ThinCard dash={dash} t={t} />
      </div>
    </>
  )
}

// ------------------------------------------------------------------ cars that came to market, by month
function MonthsCard({ dash, t }: { dash: Dash; t: Tokens }) {
  const rb = dash.proto.returns_by_month
  const last12 = rb.slice(-12).reduce((s, r) => s + r.cars, 0), prev12 = rb.slice(-24, -12).reduce((s, r) => s + r.cars, 0)
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.grid } },
      formatter: (ps: { dataIndex: number }[]) => `${monthName(rb[ps[0].dataIndex].m)}<br><b>${nf(rb[ps[0].dataIndex].cars)} cars</b>` },
    grid: { left: 0, right: 8, top: 12, bottom: 36, containLabel: true },
    xAxis: { type: 'category', data: rb.map(r => r.m), ...axisStyle(t),
      axisLabel: { ...axisStyle(t).axisLabel, formatter: (m: string) => m.endsWith('-01') ? m.slice(0, 4) : '', interval: 0 } },
    yAxis: { type: 'value', ...axisStyle(t), axisLine: { show: false } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 4, height: 16, borderColor: t.line, fillerColor: t.grid,
      handleStyle: { color: t.surface, borderColor: t.axis }, moveHandleStyle: { color: t.axis }, labelFormatter: '',
      dataBackground: { lineStyle: { color: t.axis }, areaStyle: { color: t.grid } } }],
    series: [{ type: 'bar', color: t.series, barCategoryGap: '20%', itemStyle: { borderRadius: [2, 2, 0, 0] },
      data: rb.map(r => r.cars) }],
  }), [rb, t])
  return (
    <Card className="span-7" about="Cars that came to market, by month"
      title="Cars returning to market by month" sub={<>{nf(last12)} in the last 12 months, {nf(prev12)} the year before</>}
      layers={['proto']}
      info={{
        serves: 'checking the forecast against what actually arrived. Drag the slider or scroll to zoom.',
        source: 'real dates from the Dutch register: the prototype\'s cars changing keeper after their first 3 months.',
        caveat: 'only the latest keeper change is visible, so every count is a lower bound.',
      }}
      twin={{ cols: ['Month', 'Cars'], num: [false, true], tall: true, rows: rb.map(r => [r.m, nf(r.cars)]) }}>
      <Chart option={option} height={200} label={`Cars coming to market by month, ${monthName(rb[0].m)} to ` +
        `${monthName(rb[rb.length - 1].m)}; ${nf(last12)} in the last 12 months`} />
    </Card>
  )
}

// ------------------------------------------------------------------ what arrives by model; a bar filters the work list
function ModelsCard({ dash, t, model, setModel }: { dash: Dash; t: Tokens; model: Model | null; setModel: (m: Model | null) => void }) {
  const all = dash.proto.supply_by_model, bm = all.slice(0, 12)   // the chart's 12 largest; its table lists all
  const cur = useRef(model)
  cur.current = model
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { dataIndex: number }) => {
      const r = bm[p.dataIndex]
      return `${cap(r.make)} ${r.model}, ${nf(r.cars)} cars<br><b>${eurMraw(r.expected_eur)}</b>, ${nf(r.expected_3m, 1)} cars in 3 months`
    } },
    grid: { left: 0, right: 56, top: 0, bottom: 0, containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: bm.map(r => `${cap(r.make)} ${r.model}`), ...axisStyle(t),
      axisLine: { show: false }, axisLabel: { ...axisStyle(t).axisLabel, color: t.ink, interval: 0 } },
    series: [{ type: 'bar', barWidth: 10, cursor: 'pointer',
      data: bm.map(r => ({ value: r.expected_eur, itemStyle: { color: t.series, borderRadius: [0, 4, 4, 0],
        opacity: model == null || same(r, model) ? 1 : 0.3 } })),
      label: { show: true, position: 'right', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
        formatter: (p: { value: number }) => eurMraw(p.value) } }],
  }), [bm, t, model])
  const ready = (c: ChartApi) => c.on('click', (p: { dataIndex?: number }) => {
    if (p.dataIndex == null) return
    const r = bm[p.dataIndex]
    setModel(same(r, cur.current) ? null : { make: r.make, model: r.model })
  })
  const top = bm[0]
  return (
    <Card className="span-5" about="Expected arrivals in 3 months by model, in euros"
      title="Expected arrivals by model" sub={<>Next 3 months, top: {cap(top.make)} {top.model}, {eurMraw(top.expected_eur)}</>}
      layers={['proto']}
      info={{
        serves: 'reconditioning capacity and channel plans by model. Click a bar to filter the work list; again to clear.',
        source: `the readiness engine's 3-month chance times the engine's value, summed by model: the ${bm.length} ` +
          `largest here, the ${all.length} largest in the table.`,
      }}
      twin={{ cols: ['Model', 'Cars in the book', 'Expected in 3 months', 'Expected €'], num: [false, true, true, true],
        rows: all.map(r => [`${cap(r.make)} ${r.model}`, nf(r.cars), nf(r.expected_3m, 1), eurMraw(r.expected_eur, 2)]) }}>
      <Chart option={option} height={200} onReady={ready} label={'Expected arrivals by model: ' +
        bm.map(r => `${r.make} ${r.model} ${eurMraw(r.expected_eur)}`).join('; ')} />
    </Card>
  )
}

// ------------------------------------------------------------------ the two work lists: incoming stock, the pricing desk
function WorkCard({ dash, model, setModel }: { dash: Dash; model: Model | null; setModel: (m: Model | null) => void }) {
  const P = dash.proto, pr = dash.group.prices
  const [list, setList] = useState<'in' | 'desk'>('in')
  const [showAll, setShowAll] = useState(false)
  const [prop, setProp] = useState<Record<number, string>>({})
  const { last } = useActions()
  useEffect(() => setShowAll(false), [model, list])
  const supply = useMemo(() => [...P.supply_queue, ...P.supply_queue_more], [P])
  const S = useMemo(() => scaleOf(supply), [supply]), S2 = useMemo(() => scaleOf(P.pricing_desk), [P])
  const keep = (r: Model) => model == null || same(r, model)
  const inRows = supply.filter(keep), deskRows = P.pricing_desk.filter(keep)
  const n = list === 'in' ? inRows.length : deskRows.length
  const inCols: Col<SupplyRow>[] = [
    { h: 'Car', cls: 'tdcar', get: r => <CarButton id={r.car} />, sort: r => r.car },
    { h: 'Car model', get: r => <ModelCell r={r} thinCars={pr.thin_switch_cars} />, sort: r => r.make + r.model },
    { h: 'Why now', get: r => <><TypeChip type={r.reason_type} list={P.reason_types.timing} />
      <span className="sub nowrap">{nf(r.age)} months old</span></>, sort: r => r.reason_type },
    { h: 'Chance in 3 months', get: r => <ChanceCell r={r} />, sort: r => r.p3, num: true },
    { h: 'Value (80% band)', get: r => <ValueCell r={r} S={S} />, sort: r => r.mark, num: true },
    { h: 'Expected €', get: r => eur(r.expected), sort: r => r.expected, num: true },
    { h: 'Route (simulated)', cls: 'tdin', get: r => <RouteAct r={r} /> },   // the rule's advice is the select's prompt
  ]
  const deskCols: Col<DeskRow>[] = [
    { h: 'Car', cls: 'tdcar', get: r => <CarButton id={r.car} />, sort: r => r.car },
    { h: 'Car model', get: r => <ModelCell r={r} thinCars={pr.thin_switch_cars} noThin />, sort: r => r.make + r.model },
    { h: 'Came back', get: r => <span className="nowrap">{r.came_back}</span>, sort: r => r.came_back },
    { h: "Engine's value (80% band)", get: r => <ValueCell r={r} S={S2} />, sort: r => r.mark, num: true },
    { h: 'In-house margin left', get: r => <MarginLeft r={r} asOf={P.as_of} pr={pr} />, sort: r => daysBack(r, P.as_of),
      num: true },
    { h: 'Type a first proposal, then log it (simulated)', cls: 'tdin', get: r => <span className="act-row">
      <input type="number" className="prop" min={0} step={100} placeholder="€" disabled={!!last('desk', String(r.car))}
        aria-label={`First proposal for car ${r.car}`} value={prop[r.car] ?? ''}
        onChange={e => setProp({ ...prop, [r.car]: e.target.value })} />
      <LogPrice r={r} v={Number(prop[r.car])} /></span> },
    { h: "The rule's answer", get: r => <Answer r={r} v={Number(prop[r.car])} S={S2} types={P.reason_types.desk} />,
      sort: r => r.reason_type },
  ]
  return (
    <Card className="span-12" about="The used-car business's two work lists"
      title={list === 'in' ? 'Incoming stock' : 'Pricing desk'}
      sub={list === 'in' ? 'Likeliest, dearest arrivals first'
        : <>The {nf(P.pricing_desk.length)} dearest of {nf(P.desk_count)} back this quarter, priced inside the tied band</>}
      layers={['proto']}
      tools={<div className="q-tools">
        <div className="seg" role="group" aria-label="Work list">
          <button type="button" aria-pressed={list === 'in'} onClick={() => setList('in')}>Incoming stock</button>
          <button type="button" aria-pressed={list === 'desk'} onClick={() => setList('desk')}>Pricing desk</button>
        </div>
        {model && <button type="button" className="text-btn" onClick={() => setModel(null)}>
          Clear {cap(model.make)} {model.model}</button>}
        {n > 10 && <button type="button" className="text-btn" aria-expanded={showAll}
          onClick={() => setShowAll(!showAll)}>{showAll ? 'Show the first 10' : `Show all ${nf(n)}`}</button>}
      </div>}
      info={list === 'in' ? {
        serves: 'preparing for the cars most likely to come to market in the next 3 months, ranked by the euros ' +
          'expected to arrive (chance × value), before they arrive. Each row: plan the lease return (a reconditioning slot and a price) or ' +
          'pre-price the likely trade-in, then route the car; a little-history car also needs a pricer\'s sign-off. Routing is ' +
          'simulated in this page, with an undo.',
        source: `listed: the ${nf(P.supply_queue.length)} largest by expected euros and each top model's 15 largest, ` +
          `${nf(supply.length)} cars. Bars: the value's 80% band on a ±${nf(100 * S)}% scale. Why now, one of a ` +
          `fixed list: ${typeList(P.reason_types.timing)}.`,
        caveat: 'expensive cars lead: a day in stock costs in proportion to the car\'s value, and so does the ' +
          'in-house margin. The chance\'s band is sampling error only, so it is shown, not ranked on. The group\'s ' +
          'contract end dates would make the timing exact.',
      } : {
        serves: 'setting each retail price inside the band tied to the engine\'s uncertainty. The pricer types a ' +
          'first proposal in euros; the allowed range appears after it, and the first proposal is logged before the cap.',
        source: `margin left: in-house retail keeps ${pc(pr.channel_after, 1)} of the price over the trade after all ` +
          `costs (group), gone after ${nf(pr.channel_breakeven_days)} extra days; days back count more than the extra ` +
          'days, so it is a floor. ' +
          `The cap by age from the override-band analysis (±${nf(pr.band_avg_pct, 0)}% on average, wider where ` +
          `the engine is less sure). A day in stock costs about ${eur(pr.day_cost, 2)} per €10,000 of car ` +
          `(${eur(pr.day_cost_low, 2)}–${eur(pr.day_cost_high, 2)}), measured on young cars. Each car's rule, one ` +
          `of a fixed list: ${typeList(P.reason_types.desk)}.`,
        caveat: 'the range is hidden until a proposal is typed so the proposal is the pricer\'s own: the band decision ' +
          '(a Phase 3 gate) reads first proposals logged before the cap, and people move less than a cap allows.',
      }}>
      {list === 'in'
        ? <Queue key="in" rows={inRows} rowKey={r => r.car} cols={inCols} first={4} label="Incoming stock" tall all={showAll} setAll={setShowAll}
          empty="No listed car of this model." />
        : <Queue key="desk" rows={deskRows} rowKey={r => r.car} cols={deskCols} first={3} label="Pricing desk" tall all={showAll} setAll={setShowAll}
          empty="No car of this model came back this quarter." />}
    </Card>
  )
}

// routing an incoming car (simulated, with an undo): the rule's advice is the prompt; the choice joins the car's record
const ROUTES: Record<string, string> = {
  prep: 'routed: prepare (a reconditioning slot and a price)', auction: 'routed: to auction', retail: 'routed: to in-house retail',
}
function RouteAct({ r }: { r: SupplyRow }) {
  const { log, undo, last } = useActions()
  const a = last('incoming', String(r.car))
  return (
    <span className="act-row">
      <select className="act" value="" aria-label={`Route car ${r.car}`}
        onChange={e => { const k = e.target.value
          if (k) log({ queue: 'incoming', row: String(r.car), car: r.car, what: ROUTES[k],
            detail: `${r.route}; expected ${eur(r.expected)}`, eur: null }) }}>
        <option value="">{a ? a.what[0].toUpperCase() + a.what.slice(1) : r.action.split('; ')[0]}</option>
        <option value="prep">Prepare: slot and price</option>
        <option value="auction">Route to auction</option>
        <option value="retail">Route to in-house retail</option>
      </select>
      {a && <button type="button" className="text-btn" onClick={() => undo(a.key)} aria-label={`Undo the route for car ${r.car}`}>
        Undo</button>}
    </span>
  )
}

// logging a first proposal: the rule's answer is kept with it, and feeds the CFO's pricing-alignment reading
function LogPrice({ r, v }: { r: DeskRow; v: number }) {
  const { log, undo, last } = useActions()
  const a = last('desk', String(r.car))
  if (a) return <button type="button" className="text-btn" onClick={() => undo(a.key)}
    aria-label={`Undo the logged price for car ${r.car}`}>Undo</button>
  if (!(v > 0)) return null
  const lo = r.mark * (1 - r.cap_pct / 100), hi = r.mark * (1 + r.cap_pct / 100), inside = v >= lo && v <= hi
  return <button type="button" className="log" onClick={() => log({ queue: 'desk', row: String(r.car), car: r.car,
    what: 'price logged', eur: v, inside: r.thin ? null : inside,
    detail: r.thin ? 'little history: a person signs off' : inside ? `inside ±${nf(r.cap_pct, 1)}%` : `outside ±${nf(r.cap_pct, 1)}%: a manager decides` })}>
    Log</button>
}

// days since a car came back, to the as-of date
const daysBack = (r: DeskRow, asOf: string) => Math.round((Date.parse(asOf) - Date.parse(r.came_back)) / 864e5)
// the in-house margin a car still has at least: the margin after all costs, less a day's share for every day it has
// been back (the break-even counts extra days beyond a normal sale, so days back overstate them: a floor, not a point)
function MarginLeft({ r, asOf, pr }: { r: DeskRow; asOf: string; pr: Dash['group']['prices'] }) {
  const d = daysBack(r, asOf), be = pr.channel_breakeven_days
  const left = Math.max(0, pr.channel_after * (1 - d / be))
  return <>
    <span className="nowrap">{d > be ? <Status kind="warn">check the trade</Status> : <>≥ {pc(left, 1)} of the price</>}</span>
    <span className="sub nowrap">day {nf(d)} of {nf(be)}, {eur(r.day_cost, 2)} a day</span></>
}

// the rule's answer to a proposal: a bullet graph (Few) of the tied cap inside the engine's band, the proposal a heavy
// mark, and the answer in words
function Answer({ r, v, S, types }: { r: DeskRow; v: number; S: number; types: [string, string][] }) {
  if (!(v > 0)) return <><TypeChip type={r.reason_type} list={types} /><span className="sub nowrap">{r.action}</span></>
  const lo = r.mark * (1 - r.cap_pct / 100), hi = r.mark * (1 + r.cap_pct / 100), inside = v >= lo && v <= hi
  const w = 96, h = 14, x = (u: number) => Math.max(0, Math.min(w, w / 2 + (w / 2) * ((u / r.mark) - 1) / S))
  const b: Banded = r
  return (
    <span className="answer">
      <svg className="vb" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img"
        aria-label={`Proposal ${eur(v)} against the allowed ${eur(lo)} to ${eur(hi)}`}>
        <rect x={x(b.low)} y="3" width={x(b.high) - x(b.low)} height={h - 6} rx="2" className="vb-band" />
        <rect x={x(lo)} y="1" width={x(hi) - x(lo)} height={h - 2} rx="2" className="ans-cap" />
        <rect x={x(r.mark) - 1} y="0" width="2" height={h} className="vb-tick" />
        <rect x={x(v) - 2} y="0" width="4" height={h} rx="1" className="ans-prop" />
      </svg>
      {r.thin ? <Status kind="warn">Little history: a person signs off</Status>
        : inside ? <Status kind="ok">Inside: price at {eur(v)}</Status>
          : <Status kind="crit">Outside ±{nf(r.cap_pct, 1)}%: a manager decides</Status>}
      <span className="sub nowrap">allowed {eur(lo)}–{eur(hi)}</span>
    </span>
  )
}

// ------------------------------------------------------------------ thin slices: models by cars in the book
function ThinCard({ dash, t }: { dash: Dash; t: Tokens }) {
  const th = dash.proto.thin, sw = dash.group.prices.thin_switch_cars
  const bins = [[1, 1], [2, 9], [10, 49], [50, sw - 1], [sw, 999], [1000, 4999], [5000, Infinity]] as const
  const counts = bins.map(([a, b]) => th.counts.filter(c => c >= a && c <= b).length)
  const name = ([a, b]: readonly [number, number]) => b === Infinity ? `${nf(a)}+` : a === b ? nf(a) : `${nf(a)}–${nf(b)}`
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { dataIndex: number }) =>
      `${name(bins[p.dataIndex])} cars in the book<br><b>${counts[p.dataIndex]} models</b>` },
    grid: { left: 0, right: 8, top: 20, bottom: 20, containLabel: true },
    xAxis: { type: 'category', data: bins.map(name), ...axisStyle(t), name: 'cars of the model in the book',
      nameLocation: 'middle', nameGap: 24, nameTextStyle: { color: t.ink2, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      axisLabel: { ...axisStyle(t).axisLabel, interval: 0, fontSize: 12 } },
    yAxis: { type: 'value', ...axisStyle(t), axisLine: { show: false } },
    series: [{ type: 'bar', barWidth: '60%',
      data: counts.map((c, i) => ({ value: c, itemStyle: { color: bins[i][1] < sw ? t.series : t.deemph, borderRadius: [4, 4, 0, 0] } })),
      label: { show: true, position: 'top', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      markArea: { silent: true, itemStyle: { color: t.grid },
        label: { position: 'insideTopLeft', color: t.ink2, fontFamily: 'IBM Plex Sans', fontSize: 12, formatter: `under ${nf(sw)}` },
        data: [[{ xAxis: name(bins[0]) }, { xAxis: name(bins[3]) }]] } }],
  }), [th, t])   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Card className="span-12" about="Models by cars in the book, against the little-history switch"
      title="Models by cars in the book"
      sub={<>{nf(th.models)} of {nf(th.of_models)} under {nf(sw)} cars, a person signs off their price</>}
      layers={['proto']}
      info={{
        serves: 'a person\'s sign-off where the engine has little local history (new markets, brands, electric lines).',
        source: `${nf(th.cars)} cars in the little-history models; blue: under the switch.`,
        caveat: 'the engine\'s own switch counts local listings, not a book: this is a stand-in to show where sign-off would fall.',
      }}
      twin={{ cols: ['Cars of the model in the book', 'Models', 'Little history'], num: [false, true, false],
        rows: bins.map((b, i) => [name(b), nf(counts[i]), b[1] < sw ? 'yes' : '']) }}>
      <Chart option={option} height={160} label={`Models by cars in the book: ${nf(th.models)} of ${nf(th.of_models)} under ${nf(sw)}`} />
    </Card>
  )
}
