import { useEffect, useMemo, useRef, useState } from 'react'
import type { Dash, UpgradeRow } from '../data'
import { Chart, type ChartApi, type ChartOption } from '../Chart'
import { axisStyle, base, type Tokens } from '../tokens'
import { eur, monthName, nf, pc, signed } from '../format'
import { Band, Card, ChanceCell, ModelCell, Queue, Status, Tile, TypeChip, ValueCell, scaleOf, typeList, type Col } from '../ui'
import type { ViewId } from '../views'
import { CarButton } from '../Drawer'
import { useActions } from '../actions'

// Captive finance (leak 2, the moment nobody catches; and the residual set at signing), opening on the retention
// team's day: the queue handed to the finance partner, the calls by contract age, and the level's charge moved by the
// header's slider. The readiness curve's facts sit in the calls card's info; what the level did to returned leases is
// in the Programme office; pulling an upgrade forward is a worked example for the deck.

type Props = { dash: Dash; t: Tokens; level: number; open: (v: ViewId) => void }

// the level against its three-year average, moved by the slider: every month's level is in the book series
export function levelState(dash: Dash, level: number) {
  const bk = dash.proto.book
  const past = bk.slice(-37, -1).map(r => r.level)
  const avg = past.reduce((a, b) => a + b, 0) / past.length
  const cut = [...past].sort((a, b) => a - b)[11]          // the 12th of 36 months: the cold third's edge
  const now = bk[bk.length - 1].level * (1 + level / 100)
  const gap = (x: number) => 100 * (x / avg - 1)
  return { past: bk.slice(-37, -1).map(r => ({ m: r.m, gap: gap(r.level), level: r.level })), avg, now, gapNow: gap(now),
    cutGap: gap(cut), cold: now < avg, coldThird: now <= cut, m: bk[bk.length - 1].m }
}

export function Finance({ dash, t, level }: Props) {
  const P = dash.proto, u = P.upgrade
  const L = levelState(dash, level)
  const [age, setAge] = useState<number | null>(null)
  return (
    <>
      <Band compact title="Captive finance" role="retention and residual risk" info={{
        serves: 'the finance arm and its partner banks (leak 2: the moment nobody catches; and the residual set at ' +
          'signing). Credit decisions never appear here. This business pays the second internal price. Decides the ' +
          'upgrade timing passed to the partner, the residual at signing (with the residual-value committee), and the ' +
          'monthly re-mark with its level charge.' }}>
        {u.by_age.map(x => <Tile key={x.age} v={nf(x.queued)} l="To call" note={`at ${x.age} months`}
          onClick={() => setAge(age === x.age ? null : x.age)} />)}
        <Tile v={signed(L.gapNow, 2)} l="Market level"
          note={level === 0 ? 'against its three-year average' : `at a ${signed(level, 0)} move`}
          status={<Status kind="warn">{L.cold ? 'raise the charge' : 'hold the charge'}</Status>} />
      </Band>
      <div className="wrap grid">
        <UpgradeQueue dash={dash} age={age} setAge={setAge} />
        <CallsCard dash={dash} t={t} age={age} setAge={setAge} />
        <LevelCard dash={dash} level={level} />
      </div>
    </>
  )
}

// ------------------------------------------------------------------ calls by contract age; an age filters the queue
// the wave a flagged age belongs to, and how far from it: from the car's age alone (the prototype has no contract dates)
const waveOf = (age: number) => age >= 54 ? 60 : 48
export function timing(age: number) {
  const w = waveOf(age), d = w - age
  return d > 0 ? `the ${w}-month wave in ${d === 1 ? 'a month' : `${d} months`}`
    : d === 0 ? `at the ${w}-month wave` : `${-d === 1 ? 'a month' : `${-d} months`} past the ${w}-month wave`
}
function CallsCard({ dash, t, age, setAge }: { dash: Dash; t: Tokens; age: number | null; setAge: (a: number | null) => void }) {
  const u = dash.proto.upgrade, ba = u.by_age, rc = dash.proto.ready_curve
  const top = rc.reduce((a, x) => x.p3 > a.p3 ? x : a)
  const soon = [...ba].filter(x => waveOf(x.age) > x.age).sort((a, b) => (waveOf(a.age) - a.age) - (waveOf(b.age) - b.age))[0] ?? ba[0]
  const cur = useRef(age)
  cur.current = age
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { dataIndex: number }) => {
      const x = ba[p.dataIndex]
      return `<b>${x.age} months</b>: ${timing(x.age)}<br>${nf(x.queued)} to call, of ${nf(x.financed)} financed by the ` +
        `captive (the rest held out by the pilot); ${nf(x.flagged)} flagged`
    } },
    grid: { left: 0, right: 96, top: 0, bottom: 0, containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: ba.map(x => `${x.age} months`), ...axisStyle(t),
      axisLine: { show: false }, axisLabel: { ...axisStyle(t).axisLabel, color: t.ink } },
    series: [{ type: 'bar', barWidth: 16, cursor: 'pointer',
      data: ba.map(x => ({ value: x.queued, itemStyle: { color: t.series, borderRadius: [0, 4, 4, 0],
        opacity: age == null || age === x.age ? 1 : 0.3 } })),
      label: { show: true, position: 'right', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
        formatter: (p: { dataIndex: number }) => `${nf(ba[p.dataIndex].queued)} of ${nf(ba[p.dataIndex].financed)}` } }],
  }), [ba, t, age])
  const ready = (c: ChartApi) => c.on('click', (p: { dataIndex?: number }) => {
    if (p.dataIndex == null) return
    const a = ba[p.dataIndex].age
    setAge(cur.current === a ? null : a)
  })
  return (
    <Card className="span-6" about="Calls by contract age: customers to call at each flagged age"
      title="Calls by contract age" sub={<>{nf(soon.queued)} reach {timing(soon.age)}</>} layers={['proto']}
      info={{
        serves: 'planning the finance partner\'s calls: how many customers each flagged age brings, and when their ' +
          'wave comes. Click a bar to filter the queue; again to clear.',
        source: `the readiness engine (X4) on real Dutch register ages: the chance of coming to market in 3 months ` +
          `peaks at the lease-end waves (${pc(top.p3, 1)} at ${top.age} months); the flagged ages are the top tenth ` +
          `by chance (${pc(u.flag_cut, 1)} and above).`,
        caveat: 'timing from the car\'s age alone: the group\'s contract end dates would make it exact. Bars: the ' +
          'calls in the queue, the pilot\'s treated arm; labels: of every customer the captive finances at that age.',
      }}
      twin={{ cols: ['Age', 'Timing', 'Flagged', 'Financed by the captive', 'To call (the treated arm)'],
        num: [true, false, true, true, true],
        rows: ba.map(x => [`${x.age} months`, timing(x.age), nf(x.flagged), nf(x.financed), nf(x.queued)]) }}
      action="Click an age to filter the queue.">
      <Chart option={option} height={132} onReady={ready} label={'Customers to call by flagged age: ' +
        ba.map(x => `${x.age} months ${nf(x.queued)} to call of ${nf(x.financed)}`).join('; ')} />
    </Card>
  )
}

// the queue's log: the timing sent to the finance partner, then the outcome it reports (simulated, with an undo)
const OUTCOMES: Record<string, string> = {
  sent: 'timing sent to the partner', up: 'partner: upgraded', later: 'partner: call back later', no: 'partner: declined',
}
function UpgradeAct({ r }: { r: UpgradeRow }) {
  const { log, undo, last } = useActions()
  const a = last('upgrade', String(r.car))
  return (
    <span className="act-row">
      <select className="act" value="" aria-label={`Log for car ${r.car}`}
        onChange={e => { const k = e.target.value
          if (k) log({ queue: 'upgrade', row: String(r.car), car: r.car, what: OUTCOMES[k],
            detail: `${r.age} months: ${timing(r.age)}`, eur: null }) }}>
        <option value="">{a ? `${a.what[0].toUpperCase()}${a.what.slice(1)}` : 'Choose'}</option>
        {Object.entries(OUTCOMES).map(([k, v]) => <option key={k} value={k}>{v[0].toUpperCase() + v.slice(1)}</option>)}
      </select>
      {a && <button type="button" className="text-btn" onClick={() => undo(a.key)} aria-label={`Undo the last log for car ${r.car}`}>
        Undo</button>}
    </span>
  )
}

// ------------------------------------------------------------------ the level charge: a number line the slider moves
function LevelCard({ dash, level }: { dash: Dash; level: number }) {
  const pr = dash.group.prices
  const L = levelState(dash, level), L0 = levelState(dash, 0)
  const gaps = [...L.past.map(x => x.gap), L.gapNow, L.cutGap, 0]
  const lo = Math.floor(Math.min(...gaps) - 1), hi = Math.ceil(Math.max(...gaps) + 1)
  const W = 480, x = (g: number) => 12 + (W - 24) * (g - lo) / (hi - lo)
  const step = hi - lo > 20 ? 10 : hi - lo > 8 ? 2 : 1
  const ticks: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v)
  const state = L.coldThird ? 'raise the charge, add the cold premium' : L.cold ? 'raise the charge' : 'hold the charge'
  return (
    <Card className="span-6" about="The level against its three-year average, and the charge it sets"
      title="Market level against its three-year average"
      sub={<>{level === 0 ? '' : `At a ${signed(level, 0)} move: `}{pc(Math.abs(L.gapNow), 2)}{' '}
        {L.gapNow < 0 ? 'below' : 'above'}: {state}</>}
      layers={['group', 'proto']}
      info={{
        serves: 're-marking the level monthly and pricing it into every new contract (Finance risk signs off). The ' +
          'rule reads the sign of the gap, not its size; the committee sees both. The header\'s slider moves the level.',
        source: `customer-option contracts: ${pc(pr.p2_option_pct, 2)} of the residual (${eur(pr.p2_option_eur)} on a ` +
          `48-month contract). Buy-back contracts: +${nf(pr.p2_cold_pts, 2)} points of the residual in the cold third, ` +
          `plus ${pc(pr.p2_tail_pct, 2)} a year to hold the tail (group). The level: the Dutch index in the prototype.`,
        caveat: 'the index is official data and understates the level a lessor meets, so the charge is a floor.',
      }}
      twin={{ cols: ['Month', 'Level', 'Against the three-year average'], num: [false, true, true],
        rows: [...L0.past.map(p => [p.m, nf(p.level, 4), signed(p.gap, 2)]), [L0.m + ' (now)', nf(L0.now, 4), signed(L0.gapNow, 2)],
          ...(level === 0 ? [] : [[`${L.m} at a ${signed(level, 0)} move`, nf(L.now, 4), signed(L.gapNow, 2)]])] }}>
      <div className="chart numline">
        <svg viewBox={`0 0 ${W} 96`} role="img" aria-label={`The level ${signed(L.gapNow, 2)} against its three-year ` +
          `average; the cold third below ${signed(L.cutGap, 2)}; the past 36 months from ${signed(Math.min(...L.past.map(p => p.gap)), 1)} ` +
          `to ${signed(Math.max(...L.past.map(p => p.gap)), 1)}`}>
          <rect x={x(lo)} y={34} width={x(L.cutGap) - x(lo)} height={20} className="z-third" />
          <rect x={x(L.cutGap)} y={34} width={Math.max(0, x(0) - x(L.cutGap))} height={20} className="z-cold" />
          <rect x={x(0)} y={34} width={x(hi) - x(0)} height={20} className="z-hot" />
          {L.past.map(p => <line key={p.m} x1={x(p.gap)} x2={x(p.gap)} y1={38} y2={50} className="nl-past" />)}
          <line x1={x(0)} x2={x(0)} y1={28} y2={60} className="nl-zero" />
          {ticks.map(v => <text key={v} x={x(v)} y={74} textAnchor="middle" className="nl-tick">{signed(v, 0)}</text>)}
          {level !== 0 && <g className="nl-mark ghost" style={{ transform: `translateX(${x(L0.gapNow)}px)` }}>
            <circle cx={0} cy={44} r={6} /></g>}
          <g className="nl-mark" style={{ transform: `translateX(${x(L.gapNow)}px)` }}>
            <circle cx={0} cy={44} r={7} />
            <text x={0} y={22} textAnchor="middle" className="nl-label">
              {level === 0 ? monthName(L.m) : `${signed(level, 0)} move`}: {signed(L.gapNow, 2)}</text>
          </g>
        </svg>
        <ul className="nl-key">
          <li><i className="z-third" />Cold third: raise the charge; buy-back +{nf(pr.p2_cold_pts, 2)} points</li>
          <li><i className="z-cold" />Cold: raise the charge</li>
          <li><i className="z-hot" />Hot: hold the charge</li>
          <li><i className="k-past" />The past 36 months</li>
        </ul>
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ the upgrade queue
function UpgradeQueue({ dash, age, setAge }: { dash: Dash; age: number | null; setAge: (a: number | null) => void }) {
  const P = dash.proto, u = P.upgrade, pl = u.pilot, types = P.reason_types.timing
  const [showAll, setShowAll] = useState(false)
  useEffect(() => setShowAll(false), [age])
  const all = useMemo(() => [...P.upgrade_queue, ...P.upgrade_queue_more], [P])
  const S = useMemo(() => scaleOf(all), [all])
  const rows = all.filter(r => age == null || r.age === age)
  const cols: Col<UpgradeRow>[] = [
    { h: 'Car', cls: 'tdcar', get: r => <CarButton id={r.car} />, sort: r => r.car },
    { h: 'Car model', get: r => <ModelCell r={r} thinCars={dash.group.prices.thin_switch_cars} />, sort: r => r.make + r.model },
    { h: 'Age', get: r => nf(r.age), sort: r => r.age, num: true },
    { h: 'Why now', get: r => <><TypeChip type={r.reason_type} list={types} /><span className="sub nowrap">{timing(r.age)}</span></>,
      sort: r => r.reason_type },
    { h: 'Chance in 3 months', get: r => <ChanceCell r={r} />, sort: r => r.p3, num: true },
    { h: "Car's value (80% band)", get: r => <ValueCell r={r} S={S} />, sort: r => r.mark, num: true },
    { h: 'Log (simulated)', cls: 'tdin', get: r => <UpgradeAct r={r} /> },
  ]
  const flaggedAge = age == null || u.flag_ages.includes(age)
  return (
    <Card className="span-12" about="The upgrade queue: financed customers to time"
      title="Upgrade queue" sub={<>{nf(pl.treated)} financed customers to time, likeliest first</>} layers={['proto']}
      tools={<div className="q-tools">
        <span className="held">{nf(pl.control)} held out by the pilot and not shown</span>
        <select aria-label="Filter by age" value={age ?? ''} onChange={e => setAge(e.target.value ? Number(e.target.value) : null)}>
          <option value="">All flagged ages</option>
          {u.flag_ages.map(a => <option key={a} value={a}>{a} months</option>)}
          {age != null && !u.flag_ages.includes(age) && <option value={age}>{age} months</option>}
        </select>
        {rows.length > 10 && <button type="button" className="text-btn" aria-expanded={showAll}
          onClick={() => setShowAll(!showAll)}>{showAll ? 'Show the first 10' : `Show all ${nf(rows.length)}`}</button>}
      </div>}
      info={{
        serves: 'telling the finance partner when to talk to a customer. Every row\'s action: send the timing to the ' +
          'finance partner, who owns the conversation and the consent, then log the outcome it reports. Simulated in ' +
          'this page, with an undo. Credit decisions never appear here.',
        source: `listed: the ${nf(P.upgrade_queue.length)} likeliest and each flagged age's 15 most valuable, ` +
          `${nf(all.length)} of ${nf(pl.treated)}; ranked by the chance the car comes to market in 3 months, then its ` +
          `value. Bars: the value's 80% band on a ±${nf(100 * S)}% scale. The pilot (X15's design): the group's flag ` +
          `randomised within each of the ${nf(pl.dealers)} selling dealers, two equal arms; the ${nf(pl.control)} held ` +
          'out never reach this queue (their dealers call whom they like), so the CFO can read treated against control. ' +
          `Why now, one of a fixed list: ${typeList(types)}.`,
        caveat: 'the arms here are the prototype\'s, synthetic; in the programme the pilot runs in Phase 2, in France. ' +
          'Each car\'s own equity window needs the joint ventures\' contract data. The engine predicts a car leaving its ' +
          'keeper, not a customer\'s decision.',
      }}>
      <Queue rows={rows} rowKey={r => r.car} cols={cols} first={4} label="Financed customers to time" tall all={showAll} setAll={setShowAll}
        empty={flaggedAge ? 'No listed customer matches.' : `Age ${age}: below the contact cut, so no customer is queued.`} />
    </Card>
  )
}
