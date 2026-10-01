import { useEffect, useMemo, useRef, useState } from 'react'
import type { ClaimRow, Dash, Decision } from '../data'
import { Chart, type ChartApi, type ChartOption } from '../Chart'
import { axisStyle, base, useNarrow, type Tokens } from '../tokens'
import { cap, eur, eurM, eurMraw, nf, pc, sentence } from '../format'
import { Band, Card, Queue, Status, Tile, TypeChip, typeList, type Col } from '../ui'
import type { ViewId } from '../views'
import { CarButton } from '../Drawer'
import { useActions } from '../actions'

// The new-car business (leak 1, the spend nobody can see), opening on the claims team's day: the queue a person works,
// where the claims went, why some were flagged, how late the check came, and a scheme priced with its resale cost.
// The month-end push by make is evidence for the deck; dealers appear only as a claim's counterparty (by design).

const DECISION: Record<Decision, string> = { clear: 'Cleared', hold: 'Held', review: 'In review' }
const statusOf = (d: Decision) => d === 'hold' ? <Status kind="crit">Held</Status>
  : d === 'review' ? <Status kind="warn">Review</Status> : <Status kind="ok">Cleared</Status>

type Props = { dash: Dash; t: Tokens; open: (v: ViewId) => void }

export function NewCar({ dash, t }: Props) {
  const c = dash.proto.claims, days = dash.group.kpis_targets.claim_days
  const dec = Object.fromEntries(c.decisions.map(d => [d.decision, d]))
  const flagged = dec.hold.claims + dec.review.claims
  const [reason, setReason] = useState<string | null>(null)

  return (
    <>
      <Band compact title="New-car incentives" role="the claims team" info={{
        serves: 'sales operations and the commercial committee (leak 1: the spend nobody can see). This business pays ' +
          'the first internal price. Decides claim eligibility, holding a suspected duplicate or gamed claim, mapping ' +
          'the two rulebooks, the incentive budget, and who receives an incentive.' }}>
        <Tile v={nf(flagged)} l="Waiting for a person" note={eurMraw(dec.hold.eur + dec.review.eur)} />
        <Tile v={nf(flagged - c.within_sla)} l="Past the service level" note={`of ${nf(flagged)}, ${nf(days)} working days`}
          status={<Status kind="crit">checked too late</Status>} />
        <Tile v={`${nf(c.lag_median_days)} days`} l="Median wait, filing to check" />
        <Tile v={pc(c.linked_share_value, 2)} l="Claim value linked to a car" />
      </Band>

      <div className="wrap grid">
        <QueueCard dash={dash} reason={reason} setReason={setReason} flagged={flagged} />
        <FlowCard dash={dash} t={t} />
        <ReasonsCard dash={dash} t={t} reason={reason} setReason={setReason} />
        <WaitCard dash={dash} t={t} flagged={flagged} />
        <SchemeCard dash={dash} />
      </div>
    </>
  )
}

// ------------------------------------------------------------------ the flow: each system's claims to their decision
function FlowCard({ dash, t }: { dash: Dash; t: Tokens }) {
  const c = dash.proto.claims
  const flaggedEur = c.decisions.filter(d => d.decision !== 'clear').reduce((s, d) => s + d.eur, 0)
  const colour: Record<Decision, string> = { clear: t.deemph, hold: t.crit, review: t.warn }
  const narrow = useNarrow()   // a phone: shorter labels, so the flows keep their room
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item',
      formatter: (p: { dataType: string; data: { source?: string; target?: string; name?: string; value: number; claims: number } }) =>
        p.dataType === 'edge' ? `${p.data.source} → ${p.data.target}<br><b>${eurMraw(p.data.value)}</b>, ${nf(p.data.claims)} claims`
          : `${p.data.name}<br><b>${eurMraw(p.data.value)}</b>, ${nf(p.data.claims)} claims` },
    series: [{
      type: 'sankey', left: narrow ? 72 : 156, right: narrow ? 72 : 164, top: 12, bottom: 28, nodeWidth: 12, nodeGap: 40, draggable: false,
      layoutIterations: 0, emphasis: { focus: 'adjacency' },
      label: { color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
        formatter: (p: { name: string; value: number; data: { claims: number } }) =>
          `{b|${p.name}}\n${eurMraw(p.value)}` + (narrow ? '' : `, ${nf(p.data.claims)} claims`),
        rich: { b: { fontWeight: 600, color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12 } } },
      data: [
        ...c.by_system.map(s => ({ name: `System ${s.system}`, value: s.eur, claims: s.claims,
          itemStyle: { color: t.axis }, label: { position: 'left', align: 'right' } })),
        ...c.decisions.map(d => ({ name: DECISION[d.decision], value: d.eur, claims: d.claims,
          itemStyle: { color: colour[d.decision] } })),
      ],
      links: c.by_system_decision.map(x => ({ source: `System ${x.system}`, target: DECISION[x.decision], value: x.eur,
        claims: x.claims, lineStyle: { color: colour[x.decision], opacity: x.decision === 'clear' ? 0.25 : 0.55 } })),
    }],
  }), [c, t, narrow])   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card className="span-7" about="Claims from system to decision, in euros"
      title="Claims by system and outcome" sub={<>{eurMraw(flaggedEur)} of {eurMraw(c.total_eur)} flagged, both systems</>}
      layers={['proto']}
      info={{
        serves: 'paying the right claim once, and knowing it before the money goes out.',
        source: 'the synthetic claims world (X1): two inherited systems feed one ledger.',
        caveat: `the detector ran once, on ${c.run_date}, after every claim had been paid: every hold arrives after ` +
          'the money went out. That is the case\'s "reconciled too late"; a live ledger checks at filing.',
      }}
      twin={{ cols: ['System', 'Decision', 'Claims', 'Euros'], num: [false, false, true, true],
        rows: c.by_system_decision.map(x => [`System ${x.system}`, DECISION[x.decision], nf(x.claims), eurMraw(x.eur)]) }}>
      <Chart option={option} height={204} label={'Claims in euros from each system to its decision: ' +
        c.by_system_decision.map(x => `system ${x.system} ${DECISION[x.decision].toLowerCase()} ${eurMraw(x.eur)}`).join('; ')} />
    </Card>
  )
}

// ------------------------------------------------------------------ why claims were flagged; a bar filters the queue
function ReasonsCard({ dash, t, reason, setReason }: { dash: Dash; t: Tokens; reason: string | null
  setReason: (r: string | null) => void }) {
  const rs = dash.proto.claims.reasons
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { dataIndex: number }) => {
      const r = rs[p.dataIndex]
      return `${sentence(r.reason)} (${r.decision})<br><b>${nf(r.claims)} claims</b>, ${eurMraw(r.eur)}`
    } },
    grid: { left: 0, right: 48, top: 0, bottom: 0, containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: rs.map(r => `${sentence(r.reason)} (${r.decision})`), ...axisStyle(t),
      axisLine: { show: false }, axisLabel: { ...axisStyle(t).axisLabel, color: t.ink } },
    series: [{ type: 'bar', barWidth: 12, cursor: 'pointer',
      data: rs.map(r => ({ value: r.claims, itemStyle: { color: t.series, borderRadius: [0, 4, 4, 0],
        opacity: reason == null || reason === r.reason ? 1 : 0.3 } })),
      label: { show: true, position: 'right', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
        formatter: (p: { value: number }) => nf(p.value) } }],
  }), [rs, t, reason])

  const cur = useRef(reason)   // the click handler is bound once; it reads the latest selection here
  cur.current = reason
  const ready = (ch: ChartApi) => ch.on('click', (p: { dataIndex?: number }) => {
    if (p.dataIndex == null) return
    const r = rs[p.dataIndex].reason
    setReason(cur.current === r ? null : r)
  })
  const top = rs[0]
  return (
    <Card className="span-5" about="Why claims were flagged"
      title="Flags by reason" sub={<>Top: {sentence(top.reason)}, {nf(top.claims)} claims</>} layers={['proto']}
      info={{
        serves: 'fixing the rule behind a class of errors, not only the claim. Click a bar to filter the work queue ' +
          'below to that reason; click it again to clear.',
        caveat: 'counts in the synthetic claims world. What transfers to the group is the kinds of failure, not their rates.',
      }}
      twin={{ cols: ['Reason', 'Decision', 'Claims', 'Euros'], num: [false, false, true, true],
        rows: rs.map(r => [sentence(r.reason), r.decision, nf(r.claims), eurMraw(r.eur)]) }}
      action="Click a reason to filter the queue.">
      <Chart option={option} height={204} onReady={ready} label={'Flagged claims by reason: ' +
        rs.map(r => `${r.reason} ${nf(r.claims)}`).join('; ')} />
    </Card>
  )
}

// ------------------------------------------------------------------ the work queue
function QueueCard({ dash, reason, setReason, flagged }: { dash: Dash; reason: string | null
  setReason: (r: string | null) => void; flagged: number }) {
  const P = dash.proto, types = P.reason_types.claims
  const [q, setQ] = useState('')
  const [showAll, setShowAll] = useState(false)
  useEffect(() => setShowAll(false), [reason, q])   // a new filter starts from its first ten
  const all = useMemo(() => [...P.claim_queue, ...P.claim_queue_more], [P])
  const rows = all.filter(r => (reason == null || r.reason === reason) &&
    (!q || [r.reason, r.dealer, r.programme, r.decision].some(x => x.toLowerCase().includes(q.toLowerCase()))))
  const cols: Col<ClaimRow>[] = [
    { h: 'Claim', get: r => r.claim },
    { h: 'Car', get: r => <CarButton id={r.car} />, sort: r => r.car ?? 0 },
    { h: 'Dealer, programme', get: r => <span className="nowrap">{r.dealer} <span className="muted">{r.programme}</span></span>,
      sort: r => r.dealer + r.programme },
    { h: 'System', get: r => r.system },
    { h: '€', get: r => eur(r.eur), sort: r => r.eur, num: true },
    { h: 'Status', get: r => statusOf(r.decision), sort: r => r.decision },
    { h: 'Reason', get: r => <span className="nowrap"><TypeChip type={r.reason_type} list={types} inline />
      <span className="rs">{sentence(r.reason)}</span></span>, sort: r => r.reason_type + r.reason },
    { h: 'Filed', get: r => <span className="nowrap">{r.filed}</span>, sort: r => r.filed },
    { h: 'Days to check', get: r => nf(r.checked_after_days), sort: r => r.checked_after_days, num: true },
    { h: 'Decide (simulated)', get: r => <ClaimAct r={r} /> },
  ]
  return (
    <Card className="span-12" about="Work queue: held and review claims"
      title="Claims queue" sub={<>{nf(flagged)} claims to release, hold or query</>} layers={['proto']}
      tools={<div className="q-tools">
        <select aria-label="Filter by reason" value={reason ?? ''} onChange={e => setReason(e.target.value || null)}>
          <option value="">All reasons</option>
          {dash.proto.claims.reasons.map(r => <option key={r.reason} value={r.reason}>{sentence(r.reason)}</option>)}
        </select>
        <input type="search" placeholder="Dealer or programme" aria-label="Filter the claims queue by dealer or programme"
          value={q} onChange={e => setQ(e.target.value)} />
        {rows.length > 10 && <button type="button" className="text-btn" aria-expanded={showAll}
          onClick={() => setShowAll(!showAll)}>{showAll ? 'Show the first 10' : `Show all ${nf(rows.length)}`}</button>}
      </div>}
      info={{
        serves: `a person decides each flagged claim within ${nf(dash.group.kpis_targets.claim_days)} working days; ` +
          'the undisputed part is paid; dealers can appeal. Decisions are simulated in this page: each joins the car\'s ' +
          'record, with an undo; nothing leaves the page.',
        source: `listed here: the ${nf(P.claim_queue.length)} largest flagged claims and each reason's largest, ` +
          `${nf(all.length)} of ${nf(flagged)}. Each reason has a type, one of a fixed list that says what to ask ` +
          `the dealer: ${typeList(types)}.`,
        caveat: 'a person releases, keeps holding or asks for evidence; there is no reject button. Held ' +
          'claims break a hard rule; review claims are the ones a rule cannot settle. The due ' +
          'date is the check date plus the service level in working days. Largest first; the ten shown, then all.',
      }}>
      <Queue rows={rows} rowKey={r => r.claim} cols={cols} first={5} label="Held and review claims" empty="No listed claim matches."
        all={showAll} setAll={setShowAll} />
    </Card>
  )
}

// a person's decision on a flagged claim: pay it, keep holding it, or query the dealer (hold, never reject); a query
// stays in the queue with its clock. Simulated: it joins the car's record in this page, with an undo.
const CLAIM_ACTS = {
  pay: { what: 'claim paid', chip: <Status kind="ok">Paid</Status> },
  hold: { what: 'claim kept on hold', chip: <Status kind="crit">Holding</Status> },
  query: { what: 'claim query sent to the dealer', chip: <Status kind="warn">Query sent</Status> },
} as const
function ClaimAct({ r }: { r: ClaimRow }) {
  const { log, undo, last } = useActions()
  const a = last('claims', r.claim)
  if (a) return <span className="act-row">{Object.values(CLAIM_ACTS).find(x => x.what === a.what)?.chip}
    <button type="button" className="text-btn" onClick={() => undo(a.key)} aria-label={`Undo the decision on claim ${r.claim}`}>
      Undo</button></span>
  return (
    <select className="act" value="" aria-label={`Decide claim ${r.claim}`}
      onChange={e => { const k = e.target.value as keyof typeof CLAIM_ACTS
        if (k) log({ queue: 'claims', row: r.claim, car: r.car, what: CLAIM_ACTS[k].what,
          detail: `claim ${r.claim}, ${r.programme}, system ${r.system}: ${r.reason_type} (${r.reason})`, eur: r.eur }) }}>
      <option value="">{r.action.replace(/^A person decides by/, 'By')}</option>
      <option value="pay">Pay the claim</option>
      <option value="hold">Keep holding</option>
      <option value="query">Query the dealer</option>
    </select>
  )
}

// ------------------------------------------------------------------ how long flagged claims waited for their check
function WaitCard({ dash, t, flagged }: { dash: Dash; t: Tokens; flagged: number }) {
  const c = dash.proto.claims, days = dash.group.kpis_targets.claim_days
  const sla = days / 5 * 7   // working days as calendar days (five-day weeks, no holidays)
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'axis', formatter: (ps: { data: [number, number] }[]) =>
      `${nf(ps[0].data[1])}% checked within ${nf(ps[0].data[0])} days of filing` },
    grid: { left: 0, right: 16, top: 16, bottom: 20, containLabel: true },
    xAxis: { type: 'value', min: 0, ...axisStyle(t), name: 'days from filing', nameLocation: 'middle', nameGap: 24,
      nameTextStyle: { color: t.ink2, fontFamily: 'IBM Plex Sans', fontSize: 12 } },
    yAxis: { type: 'value', min: 0, max: 100, ...axisStyle(t), axisLine: { show: false },
      axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => v + '%' } },
    series: [{ type: 'line', showSymbol: false, color: t.series, lineStyle: { width: 2 },
      data: c.lag_q.map((d, i) => [d, i]),
      markLine: { silent: true, symbol: 'none', lineStyle: { color: t.crit, width: 2, type: 'solid' },
        label: { show: true, position: 'end', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
          formatter: 'service level' },
        data: [{ xAxis: sla }] } }],
  }), [c, t, sla])
  const q = [10, 25, 50, 75, 90]
  return (
    <Card className="span-4" about="Days from filing to check, against the service level"
      title="Days from filing to check" sub={<>{nf(c.within_sla)} of {nf(flagged)} within the service level</>}
      layers={['proto']}
      info={{
        serves: `settling a claim within ${nf(days)} working days: checked at filing, not after payment.`,
        source: 'the synthetic claims world; the share of flagged claims checked by each number of days after filing.',
        caveat: `the line marks ${nf(days)} working days, drawn at ${nf(sla)} calendar days (five-day weeks, no ` +
          'holidays); the count in the title is in working days.',
      }}
      twin={{ cols: ['Share of flagged claims checked', 'Within (days of filing)'], num: [true, true],
        rows: q.map(i => [`${i}%`, nf(c.lag_q[i])]) }}>
      <Chart option={option} height={192} label={`Share of flagged claims checked by days from filing; the median ` +
        `waited ${nf(c.lag_median_days)} days; ${nf(c.within_sla)} within the service level`} />
    </Card>
  )
}

// ------------------------------------------------------------------ price a scheme: what a discount costs at resale
// For whoever designs a scheme: a make and a discount a car in, the first internal price out (the group's rate range),
// and what it would come to on the prototype's fleet leases of that make, the cars the group takes back.
function SchemeCard({ dash }: { dash: Dash }) {
  const p1 = dash.proto.price1, pr = dash.group.prices, mk = p1.by_make
  const [make, setMake] = useState(mk[0].make)
  const m = mk.find(x => x.make === make) ?? mk[0]
  const [disc, setDisc] = useState(String(m.incentive_per_car))
  const d = Math.max(0, Number(disc) || 0)
  const lo = d * pr.p1_low, hi = d * pr.p1_high
  return (
    <Card className="span-8" about="Price a scheme: a discount's resale cost, charged to sales"
      title="Resale cost of a discount" sub={<>{eur(d)} off a {cap(m.make)}: {eur(lo)} to {eur(hi)} at resale</>}
      layers={['group', 'proto']}
      info={{
        serves: 'designing a scheme with its resale cost in view: the first internal price, charged to the sales side ' +
          'on cars the group will take back.',
        source: `${nf(100 * pr.p1_low, 0)}–${nf(100 * pr.p1_high, 0)} cents of resale value per euro of incentive ` +
          `(group: measured, and the published figure). The default discount is the make's average incentive a car ` +
          `on the prototype's ${nf(p1.cars)} fleet leases.`,
        caveat: 'a range until the pilot calibrates it; our end of it is an upper bound. Charged only on cars the group ' +
          `will take back. Who needs no incentive at all stays locked until the pilot's holdout (up to ` +
          `${eurM(dash.group.targeting_upper)} a year, an upper bound).`,
      }}
      twin={{ cols: ['Make', 'Fleet leases', 'Average incentive a car', 'Charge a car at that incentive'],
        num: [false, true, true, true],
        rows: mk.map(x => [cap(x.make), nf(x.cars), eur(x.incentive_per_car), `${eur(x.charge_low)}–${eur(x.charge_high)}`]) }}>
      <div className="calc">
        <label>Make
          <select value={make} onChange={e => { const x = mk.find(y => y.make === e.target.value)!
            setMake(x.make); setDisc(String(x.incentive_per_car)) }}>
            {mk.map(x => <option key={x.make} value={x.make}>{cap(x.make)}</option>)}
          </select></label>
        <label>Discount a car (€)
          <input type="number" min={0} step={100} value={disc} onChange={e => setDisc(e.target.value)} /></label>
        <div className="calc-out"><span className="tv">{eur(lo)}–{eur(hi)}</span>
          <span className="tl">charged to sales a car</span></div>
        <div className="calc-out"><span className="tv">{eurMraw(lo * m.cars)}–{eurMraw(hi * m.cars)}</span>
          <span className="tl">on this make's {nf(m.cars)} fleet leases</span></div>
      </div>
    </Card>
  )
}
