import { useMemo, useRef, useState } from 'react'
import * as Popover from '@radix-ui/react-popover'
import type { Dash, Scenario } from '../data'
import { Chart, type ChartApi, type ChartOption } from '../Chart'
import { axisStyle, base, type Tokens } from '../tokens'
import { eur, eurM, eurMraw, monthName, nf } from '../format'
import { Band, Card, Status, Tile } from '../ui'
import type { ViewId } from '../views'

// The Programme office: the programme's own tracking, for the executive committee and Finance, kept apart from the
// tool the teams use. The roadmap with its gates, the four costed builds (none chosen), the value at risk in its two
// measures, the funnel to certified, the level's result on leases that came back, and the top risks with their answers.

type Props = { dash: Dash; t: Tokens; open: (v: ViewId) => void }
const range = (xs: number[], f: (x: number) => string) => { const lo = f(Math.min(...xs)), hi = f(Math.max(...xs)); return lo === hi ? lo : `${lo}–${hi}` }

export function Programme({ dash, t }: Props) {
  const G = dash.group, v = G.var, sc = G.programme.scenarios
  const [pick, setPick] = useState<number | null>(null)   // no build chosen: every figure shows its range
  return (
    <>
      <Band title="Programme office" info={{
        serves: 'the programme\'s own tracking, for the executive committee and Finance. Apart from the tool: the tool ' +
          'is the four team views. Decides how to build it (four costed ways, none chosen), releasing each phase\'s ' +
          'funding on its gate, and the named stop.' }}>
        <Tile v={eurM(v.expected)} l="expected a year, for the budget" />
        <Tile v={eurM(v.one_in_ten)} l="in a one-in-ten year" />
        <Tile v={eurM(v.stress)} l="stress: a Europe-wide bad year" />
        <Tile v={range(sc.map(s => s.build), x => eurM(x))} l="to build, four ways; €0 spent"
          status={<Status kind="warn">none chosen</Status>} />
      </Band>
      <div className="wrap grid overlap">
        <Roadmap dash={dash} pick={pick} setPick={setPick} />
        <BuildsCard dash={dash} t={t} pick={pick} setPick={setPick} />
        <VarCard dash={dash} t={t} />
        <FunnelCard dash={dash} t={t} />
        <ReturnsCard dash={dash} t={t} />
        <RisksCard dash={dash} />
      </div>
    </>
  )
}

// ------------------------------------------------------------------ the roadmap: four phases, gates as diamonds
function Roadmap({ dash, pick, setPick }: { dash: Dash; pick: number | null; setPick: (i: number | null) => void }) {
  const G = dash.group, sc = G.programme.scenarios, ph = G.phases, pl = G.pilot
  const months = Number(ph[ph.length - 1].months.split('–')[1])
  const at = (m: number) => `${(100 * m / months).toFixed(2)}%`
  const ends = ph.map(p => Number(p.months.split('–')[1]))
  const chosen: Scenario[] = pick == null ? sc : [sc[pick]]
  const money = (i: number) => range(chosen.map(s => s.by_phase[i]), x => eurM(x))
  const pay = (k: 'payback_plan' | 'payback_ref') => chosen.map(s => s[k])
  const mark = (k: 'payback_plan' | 'payback_ref', what: string) => {
    const xs = pay(k), lo = Math.min(...xs), hi = Math.max(...xs)
    return <div className={'rm-pay ' + k} style={{ left: at(lo), width: `calc(${at(hi)} - ${at(lo)} + 2px)` }}>
      <span>{what}: month {range(xs, x => nf(x, 0))}</span></div>
  }
  return (
    <Card className="span-12" about="The roadmap: four gated phases"
      title="Roadmap" sub={<>{nf(ph.length)} gated phases over {nf(months)} months</>} layers={['group']}
      tools={<div className="seg" role="group" aria-label="Build scenario">
        <button type="button" aria-pressed={pick == null} onClick={() => setPick(null)}>All four</button>
        {sc.map((s, i) => <button key={s.name} type="button" aria-pressed={pick === i} title={s.name}
          onClick={() => setPick(i)}>{s.name.split('.')[0]}</button>)}
      </div>}
      info={{
        serves: 'releasing each phase\'s funding only on its gate (the committee, with two reviewers from outside the ' +
          'programme). Click a diamond for the phase\'s markets, what it earns, the gate\'s checks and what happens if ' +
          'one is missed; the table view lists them all. The selector shows one build\'s money; by default all four, as ' +
          'a range.',
        source: 'the workbook\'s Benefits and Programme cost sheets; the register\'s gate targets.',
        caveat: 'every gate reads evidence its own phase produces, and each outcome (Go, Waiver with re-review, Delay, ' +
          'Back-up, Kill) is agreed in advance. No gate has been read yet.',
      }}
      twin={{ cols: ['Phase', 'Months', 'Where', 'Released', 'Earns', 'Gate check', 'If missed'], rows: G.gates.map(g => {
        const p = ph[g[0] - 1]
        return [`${p.n}. ${p.name}`, p.months, p.where, money(p.n - 1), p.earns, g[1], g[2]]
      }) }}>
      <div className="chart roadmap" role="group" aria-label="The roadmap: four phases, their gates and the payback months">
        <div className="rm-axis">{Array.from({ length: months / 6 + 1 }, (_, i) => i * 6).map(m =>
          <span key={m} style={{ left: at(m) }}>{m === 0 ? 'month 0' : m}</span>)}</div>
        <div className="rm-lane">
          {ph.map((p, i) => (
            <div key={p.n} className="rm-phase" style={{ left: at(i === 0 ? 0 : ends[i - 1]), width: `calc(${at(ends[i] - (i === 0 ? 0 : ends[i - 1]))} - 16px)` }}>
              <div className="rm-money">{money(i)} released</div>
              <div className="rm-name">{p.n}. {p.name}</div>
            </div>
          ))}
          {ph.map((p, i) => {
            const gs = G.gates.filter(g => g[0] === p.n)
            return (
              <Popover.Root key={p.n}>
                <Popover.Trigger className="rm-gate" style={{ left: at(ends[i]) }}
                  aria-label={`Gate ${p.n}: ${gs.length} ${gs.length === 1 ? 'check' : 'checks'}; open`}><span aria-hidden="true" /></Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content className="pop wide" sideOffset={8} collisionPadding={16}>
                    {/* the phase's detail, off the bar (the text diet, the user, 30 September) */}
                    <p><b>{p.n}. {p.name}</b>: {p.where}. Earns: {p.earns}.{p.n === 2 &&
                      ` Pilot: ${nf(pl.per_arm)} customers an arm; ≥ ${nf(pl.gate_pp)} points to pass.`}</p>
                    <p><b>Gate {p.n}, month {ends[i]}: {gs.length} {gs.length === 1 ? 'check' : 'checks'}</b></p>
                    <ul className="plain">{gs.map(g => <li key={g[1]}>{g[1]} <span className="muted">If missed: {g[2]}.</span></li>)}</ul>
                    <Popover.Arrow className="pop-arrow" />
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            )
          })}
        </div>
        <div className="rm-pays">
          {mark('payback_plan', 'Payback at plan')}
          {mark('payback_ref', "On large IT projects' record")}
        </div>
      </div>
      <p className="sr">Selected build: {pick == null ? 'none chosen' : sc[pick].name}</p>
    </Card>
  )
}

// ------------------------------------------------------------------ the four builds: a dot plot, none chosen
function BuildsCard({ dash, t, pick, setPick }: { dash: Dash; t: Tokens; pick: number | null; setPick: (i: number | null) => void }) {
  const sc = dash.group.programme.scenarios
  const lo = (s: Scenario) => Math.min(s.build, ...s.range.map(r => r[0])), hi = (s: Scenario) => Math.max(s.build, ...s.range.map(r => r[0]))
  const cur = useRef(pick)
  cur.current = pick
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { dataIndex: number }) => {
      const s = sc[p.dataIndex]
      return `<b>${s.name}</b>: ${eurM(s.build)}<br>payback month ${nf(s.payback_plan, 0)} at plan, ${nf(s.payback_ref, 0)} on ` +
        `the record<br>${s.range.map(([x, w]) => `${eurM(x)} ${w}`).join('<br>') || s.note}`
    } },
    grid: { left: 0, right: 64, top: 8, bottom: 0, containLabel: true },
    xAxis: { type: 'value', min: 0, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (x: number) => eurM(x, 0) } },
    yAxis: { type: 'category', inverse: true, data: sc.map(s => s.name), ...axisStyle(t),
      axisLabel: { ...axisStyle(t).axisLabel, color: t.ink } },
    series: [
      { type: 'bar', stack: 'r', silent: true, itemStyle: { color: 'transparent' }, data: sc.map(lo), tooltip: { show: false } },
      { type: 'bar', stack: 'r', silent: true, barWidth: 2, itemStyle: { color: t.axis }, data: sc.map(s => hi(s) - lo(s)),
        tooltip: { show: false } },
      { type: 'scatter', symbolSize: 14, cursor: 'pointer', data: sc.map((s, i) => ({ value: [s.build, i],
        itemStyle: { color: pick === i ? t.ink : t.series, borderColor: t.surface, borderWidth: 2 } })),
        label: { show: true, position: 'right', distance: 10, color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
          formatter: (p: { dataIndex: number }) => eurM(sc[p.dataIndex].build) } },
    ],
  }), [sc, t, pick])   // eslint-disable-line react-hooks/exhaustive-deps
  const ready = (c: ChartApi) => c.on('click', (p: { seriesIndex?: number; dataIndex?: number }) => {
    if (p.seriesIndex !== 2 || p.dataIndex == null) return
    setPick(cur.current === p.dataIndex ? null : p.dataIndex)
  })
  return (
    <Card className="span-6" about="Four ways to build it"
      title="Build cost by scenario" sub={<>{range(sc.map(s => s.build), x => eurM(x))} over 24 months</>}
      layers={['group']}
      info={{
        serves: 'choosing how to build it (the committee and Finance). One work list priced four ways; only the build ' +
          'cost and its timing change. A dot selects its build on the roadmap; the lines show what moves each build.',
        source: 'priced in-house at Eurostat\'s loaded pay for each role\'s occupation group, bought at a public ' +
          'integrator\'s rate card, in-house with AI at the gains the studies measured, and the cheapest of the three ' +
          'in each workstream. Large IT projects\' record is McKinsey-Oxford\'s. Value: five-year NPV at the group\'s ' +
          'highest pre-tax cost of capital. Workbook sheets Programme cost and Benefits.',
        caveat: 'platform and change delivery are the same in every scenario, and so are the benefits and the exit gate.',
      }}
      twin={{ cols: ['Scenario', 'Build, 24 months', 'Released at the start and each gate', 'Payback, plan (month)',
        "Payback on large IT projects' record (month)", 'Value over five years on that record', 'Lost if stopped at the first gate',
        'Floor, a year', 'What moves the build'],
        num: [false, true, false, true, true, true, true, true, false],
        rows: sc.map(s => [s.name, eurM(s.build), s.by_phase.map(x => nf(x, 1)).join(', '), nf(s.payback_plan, 0),
          nf(s.payback_ref, 0), eurM(s.value_ref), eurM(s.loss_gate1_ref), eurM(s.floor),
          s.range.map(([x, w]) => `${eurM(x)} ${w}`).join('; ') || s.note]) }}>
      <Chart option={option} height={176} onReady={ready} label={'Build cost by scenario: ' +
        sc.map(s => `${s.name} ${eurM(s.build)}`).join('; ') + '; none chosen'} />
    </Card>
  )
}

// ------------------------------------------------------------------ value at risk by leak: two measures, never added
function VarCard({ dash, t }: { dash: Dash; t: Tokens }) {
  const v = dash.group.var
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 12, itemGap: 16,
      textStyle: { color: t.ink2, fontFamily: 'IBM Plex Sans', fontSize: 12 } },
    tooltip: { ...base(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.grid } },
      valueFormatter: (x: unknown) => eurM(Number(x)) },
    grid: { left: 0, right: 64, top: 32, bottom: 0, containLabel: true },
    xAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (x: number) => eurM(x, 0) } },
    yAxis: { type: 'category', inverse: true, data: v.leaks.map(l => l.short), ...axisStyle(t),
      axisLabel: { ...axisStyle(t).axisLabel, color: t.ink, width: 140, overflow: 'break' } },
    series: [
      { name: 'Expected a year', color: t.ord1, data: v.leaks.map(l => l.expected) },
      { name: 'In a one-in-ten-year market', color: t.ord2, data: v.leaks.map(l => l.one_in_ten) },
    ].map(s => ({ ...s, type: 'bar', barWidth: 12, barGap: '20%', itemStyle: { borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
        formatter: (p: { value: number }) => eurM(p.value) } })),
  }), [v, t])
  return (
    <Card className="span-6" about="Value at risk a year by leak, in two measures"
      title="Value at risk by leak" sub="Two measures, side by side"
      layers={['group']}
      info={{
        serves: 'funding the programme and setting its budget (the committee).',
        source: 'the value-at-risk workbook (Summary sheet), built from the register.',
        caveat: `the two measures answer different questions, so they are never added. Leak 3 is small on average and ` +
          `large in a bad year, because the buy-back cars come back both ways. The stress, ${eurM(v.stress)}, sits beside the second.`,
      }}
      twin={{ cols: ['Leak', 'Expected a year', 'One year in ten'], num: [false, true, true],
        rows: [...v.leaks.map(l => [l.name, eurM(l.expected), eurM(l.one_in_ten)]), ['Total', eurM(v.expected), eurM(v.one_in_ten)]] }}>
      <Chart option={option} height={176} label={'Value at risk by leak: ' +
        v.leaks.map(l => `${l.short} ${eurM(l.expected)} expected, ${eurM(l.one_in_ten)} one year in ten`).join('; ')} />
    </Card>
  )
}

// ------------------------------------------------------------------ from at risk to certified
function FunnelCard({ dash, t }: { dash: Dash; t: Tokens }) {
  const f = dash.group.funnel, plan = f[2].eur_m, last = f[f.length - 1]
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { dataIndex: number }) =>
      `${f[p.dataIndex].step}<br><b>${eurM(f[p.dataIndex].eur_m)}</b>` },
    grid: { left: 0, right: 112, top: 0, bottom: 0, containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: f.map(x => x.step), ...axisStyle(t), axisLine: { show: false },
      axisLabel: { ...axisStyle(t).axisLabel, color: t.ink, width: 170, overflow: 'break' } },
    series: [{ type: 'bar', barWidth: 14,
      // certified: nothing yet, drawn as an empty outline the size of the plan it must fill
      data: f.map((x, i) => i === f.length - 1 && x.eur_m === 0
        ? { value: plan, itemStyle: { color: 'transparent', borderColor: t.ink2, borderWidth: 1, borderType: 'dashed', borderRadius: 4 } }
        : { value: x.eur_m, itemStyle: { color: t.series, borderRadius: [0, 4, 4, 0] } }),
      label: { show: true, position: 'right', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
        formatter: (p: { dataIndex: number }) => f[p.dataIndex].eur_m > 0 ? eurM(f[p.dataIndex].eur_m) : '€0, nothing yet' } }],
  }), [f, t, plan])
  return (
    <Card className="span-6" about="From value at risk to value certified"
      title="Benefits, from at risk to certified" sub={<>Certified by Finance: {eurM(last.eur_m, 0)} of {eurM(plan)} planned</>}
      layers={['group']}
      info={{
        serves: 'holding the programme to what Finance certifies, not to what it plans. The dashed outline is the plan ' +
          'that certification must fill.',
        source: 'the workbook\'s Benefits sheet; the large-IT-projects line applies the reference class\'s record to the plan.',
        caveat: 'reach is not benefit; plan is not certification. Nothing is certified until the programme runs: Finance ' +
          'certifies from Phase 1.',
      }}
      twin={{ cols: ['Step', '€m a year'], num: [false, true], rows: f.map(x => [x.step, eurM(x.eur_m)]) }}>
      <Chart option={option} height={176} label={'From at risk to certified: ' + f.map(x => `${x.step} ${eurM(x.eur_m)}`).join('; ')} />
    </Card>
  )
}

// ------------------------------------------------------------------ the level's part of leases that came back
function ReturnsCard({ dash, t }: { dash: Dash; t: Tokens }) {
  const lr = dash.proto.level_result, tot = dash.proto.level_result_total
  const last = dash.proto.returns_by_month[dash.proto.returns_by_month.length - 1].m
  const partial = (y: number) => String(y) === last.slice(0, 4) && !last.endsWith('-12')
  const label = (y: number) => partial(y) ? `${y}\nto ${monthName(last).split(' ')[0]}` : String(y)
  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    tooltip: { ...base(t).tooltip, trigger: 'item', formatter: (p: { dataIndex: number }) => {
      const r = lr[p.dataIndex]
      return `Came back in ${label(r.year).replace('\n', ' ')}: ${nf(r.cars)} leases<br><b>${eurMraw(r.level_part)}</b>, ${eur(r.per_car)} a car`
    } },
    grid: { left: 0, right: 8, top: 20, bottom: 0, containLabel: true },
    xAxis: { type: 'category', data: lr.map(r => label(r.year)), ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, interval: 0 } },
    yAxis: { type: 'value', ...axisStyle(t), axisLine: { show: false },
      axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => eurMraw(v, 0) } },
    series: [{ type: 'bar', barWidth: '55%', color: t.series,
      data: lr.map(r => ({ value: r.level_part, itemStyle: { borderRadius: [4, 4, 0, 0], opacity: partial(r.year) ? 0.55 : 1 } })),
      label: { show: true, position: 'top', color: t.ink, fontFamily: 'IBM Plex Sans', fontSize: 12,
        formatter: (p: { dataIndex: number }) => eur(lr[p.dataIndex].per_car) } }],
  }), [lr, t])   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Card className="span-6" about="The market level's part of leases that came back, by year"
      title="Returned leases by year" sub={<>The level's move added {eurMraw(tot.level_part)}</>} layers={['proto']}
      info={{
        serves: 'the programme\'s results: the level\'s result apart from the car\'s, contract by contract, so the ' +
          'residual-value committee can judge the charge. Bars: euros; labels: a car.',
        source: `real index and real dates (the register's keeper changes read to ${monthName(last)}); synthetic residuals.`,
        caveat: 'live contracts\' exposure needs their terms and balances from the joint ventures: not held today. ' +
          `The last year is partial.`,
      }}
      twin={{ cols: ['Came back in', 'Leases', 'Level part', 'A car'], num: [false, true, true, true],
        rows: [...lr.map(r => [label(r.year).replace('\n', ' '), nf(r.cars), eurMraw(r.level_part), eur(r.per_car)]),
          ['All', nf(tot.cars), eurMraw(tot.level_part), '']] }}>
      <Chart option={option} height={176} label={'The level part of returned leases by year: ' +
        lr.map(r => `${r.year} ${eurMraw(r.level_part)}`).join('; ')} />
    </Card>
  )
}

// ------------------------------------------------------------------ top risks, each with its answer
function RisksCard({ dash }: { dash: Dash }) {
  const rs = dash.group.risks
  return (
    <section className="card span-12" aria-labelledby="risks-h">
      <header className="card-head"><div className="card-title"><h3 id="risks-h">Top risks</h3>
        <p className="card-sub">Each with its named answer</p></div></header>
      <ul className="risks">
        {rs.map(([risk, answer]) => (
          <li key={risk}>
            <Popover.Root>
              <Popover.Trigger className="risk" aria-label={`${risk}: its answer`}>
                <Status kind="warn">{risk}</Status>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content className="pop" sideOffset={6} collisionPadding={16}>
                  <p><b>{risk}.</b> {answer}.</p>
                  <Popover.Arrow className="pop-arrow" />
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
          </li>
        ))}
      </ul>
    </section>
  )
}
