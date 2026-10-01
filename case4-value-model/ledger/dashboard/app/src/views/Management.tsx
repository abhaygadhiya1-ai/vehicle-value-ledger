import { useMemo } from 'react'
import type { Dash } from '../data'
import { Chart, type ChartOption } from '../Chart'
import { axisStyle, base, type Tokens } from '../tokens'
import { eur, eurM, eurMraw, monthName, nf, pc, signed } from '../format'
import { Band, Card, Status, Tile } from '../ui'
import type { ViewId } from '../views'
import { KpiBoard, kpiSummary, kpis, kpiTwin } from './Kpis'
import { alignment, useActions } from '../actions'

type Props = { dash: Dash; t: Tokens; level: number; open: (v: ViewId) => void }

export function Management({ dash, t, level, open }: Props) {
  const G = dash.group, P = dash.proto
  const dec = Object.fromEntries(P.claims.decisions.map(d => [d.decision, d]))
  const exp3 = P.supply_totals.reduce((s, x) => s + x.expected_3m, 0)
  const exp3eur = P.supply_totals.reduce((s, x) => s + x.expected_eur, 0)
  const now = P.book_now, lv = P.level_now
  const moved = now.book * (1 + level / 100)
  const { on, read, off } = kpiSummary(kpis(G, P).pairs)
  const al = alignment(useActions().acts)

  return (
    <>
      <Band title="Management" role="the CFO and the Vehicle Value Council" info={{
        serves: 'the CFO and the Vehicle Value Council: exposure and exceptions. Decides the level\'s price and the ' +
          'three internal prices, and reads each team\'s measures beside their guards. Car-level work lives in the ' +
          'three team views; the programme\'s own tracking is in the Programme office, apart from the tool.' }}>
        <Tile hero v={eurMraw(moved)} l={level === 0 ? `the book, ${nf(now.cars)} cars, ${monthName(now.m)}`
          : `the book at a ${signed(level, 0)} level (${level > 0 ? '+' : ''}${eurMraw(moved - now.book)})`} />
        <Tile v={signed(lv.gap_pct, 2)} l="level against its three-year average" onClick={() => open('fin')}
          status={<Status kind="warn">{lv.gap_pct < 0 ? 'raise the charge' : 'hold the charge'}</Status>} />
        <Tile v={eurMraw(dec.hold.eur + dec.review.eur)} l={`in ${nf(dec.hold.claims + dec.review.claims)} claims for a person`}
          onClick={() => open('oem')} />
        <Tile v={nf(exp3)} l={`cars due in 3 months, ${eurMraw(exp3eur)}`} onClick={() => open('resale')} />
      </Band>

      <div className="wrap grid overlap">
        <BookCard dash={dash} t={t} level={level} />
        <PricesCard dash={dash} />

        <Card className="span-12" about="KPIs beside their guards"
          title="KPIs and their guards"
          sub={off.length === 0 ? <>All {nf(read.length)} readings on target</>
            : <>{nf(on.length)} of {nf(read.length)} on target</>}
          layers={['group', 'proto']}
          info={{
            serves: 'reading the programme in its own terms. A pace or reach target is read only beside its guard; ' +
              'a reading appears only where the prototype can make one, and says what it measures.',
            source: 'targets: the register (every target has its reason there; none feeds the value at risk).',
            detail: <>The recoveries target, ≥ €{G.kpis_targets.claims_recovered}m a year, depends on the build. Days cut
              from the time to sale are read on randomised returns. The retention uplift has its guard built in: treated
              against control within dealers, in the prototype; its gate reads on {nf(G.pilot.per_arm)} customers an
              arm, in Phase 2. The pricers' reading comes from the pricing desk's logged proposals.</>,
            caveat: '"When a measure becomes a target, it ceases to be a good measure" (Strathern, 1997, after ' +
              'Goodhart). So a claim settled fast counts only if recoveries hold, days cut only if margin holds.',
          }}
          twin={kpiTwin(G, P, al)}>
          <KpiBoard g={G} p={P} al={al} />
        </Card>
      </div>
    </>
  )
}

// ------------------------------------------------------------------ the book: the level and the curve apart
function BookCard({ dash, t, level }: { dash: Dash; t: Tokens; level: number }) {
  const bk = dash.proto.book, now = dash.proto.book_now
  const lo = bk.reduce((a, r) => r.level < a.level ? r : a), hi = bk.reduce((a, r) => r.level > a.level ? r : a)
  const moved = now.book * (1 + level / 100)

  const option = useMemo<ChartOption>(() => ({
    ...base(t),
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 12, itemGap: 16,
      textStyle: { color: t.ink2, fontFamily: 'IBM Plex Sans', fontSize: 12 } },
    tooltip: { ...base(t).tooltip, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.axis } },
      formatter: (ps: { dataIndex: number }[]) => {
        const r = bk[ps[0].dataIndex]
        return `<b>${monthName(r.m)}</b>, ${nf(r.cars)} cars<br>The book ${eurMraw(r.book)}<br>` +
          `The curve alone ${eurMraw(r.curve)}<br>The level ${nf(r.level, 4)}`
      } },
    grid: { left: 0, right: 16, top: 44, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: bk.map(r => r.m), boundaryGap: false, ...axisStyle(t),
      axisLabel: { ...axisStyle(t).axisLabel, formatter: (m: string) => m.endsWith('-01') ? m.slice(0, 4) : '',
        interval: 0 } },
    yAxis: { type: 'value', ...axisStyle(t), axisLine: { show: false },
      axisLabel: { ...axisStyle(t).axisLabel, formatter: (x: number) => eurM(x / 1e6, 0) } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 4, height: 16, borderColor: t.line,
      fillerColor: t.grid, handleStyle: { color: t.surface, borderColor: t.axis },
      moveHandleStyle: { color: t.axis }, textStyle: { color: t.ink2, fontSize: 12 }, labelFormatter: '',
      dataBackground: { lineStyle: { color: t.axis }, areaStyle: { color: t.grid } } }],
    series: [
      { name: "The book at the engine's value", type: 'line', showSymbol: false, color: t.series,
        lineStyle: { width: 2 }, areaStyle: { color: t.area }, data: bk.map(r => r.book),
        markLine: { silent: true, symbol: ['none', 'arrow'], symbolSize: 8, animationDurationUpdate: 400,
          lineStyle: { color: t.ink, width: 2, type: 'solid' }, label: { show: false },   // the tile and the action line say it
          data: level === 0 ? [] : [[{ coord: [now.m, now.book] }, { coord: [now.m, moved] }]] } },
      { name: 'The curve alone (the level held)', type: 'line', showSymbol: false, color: t.deemph,
        lineStyle: { width: 2, type: [4, 3] }, data: bk.map(r => r.curve) },
    ],
  }), [bk, t, level, now, moved])

  return (
    <Card className="span-5" about="The book by month, the level and the curve apart"
      title="Book value by month"
      sub={<>Level alone: {pc(100 * lo.level, 1)} to {pc(100 * hi.level, 1)} of curve value</>}
      layers={['proto']}
      info={{
        serves: 'provisioning and pricing the market level (Finance risk signs off). The level is priced and ' +
          're-marked monthly, never forecast.',
        source: `the prototype's book: ${nf(now.cars)} real Dutch group cars at the engine's value (real catalogue ` +
          `prices and index, ${dash.proto.as_of}).`,
        caveat: 'it shows how the ledger splits a value into the car and the market; it is not the group\'s buy-back ' +
          'book, whose exposure is under Programme.',
      }}
      twin={{ cols: ['Month', 'Cars', 'The book', 'The curve alone', 'The level'], tall: true,
        rows: bk.map(r => [r.m, nf(r.cars), eurMraw(r.book), eurMraw(r.curve), nf(r.level, 4)]),
        num: [false, true, true, true, true] }}
      action={level === 0 ? 'Move the level above.'
        : `At ${signed(level, 0)}, every car moves at once: ${eurMraw(moved - now.book)}.`}>
      <Chart option={option} height={236}
        label={`The book by month from ${monthName(bk[0].m)} to ${monthName(now.m)}, ${eurMraw(now.book)} now, with ` +
          'the curve alone beside it'} />
    </Card>
  )
}

// ------------------------------------------------------------------ the three internal prices, as a table
// (the AI look, part 2: a finance team reads this as rows, so no drawn arrows; euros right-aligned, as GOV.UK's tables)
function PricesCard({ dash }: { dash: Dash }) {
  const pr = dash.group.prices, tc = dash.group.tied_caps, p1 = dash.proto.price1
  // one short line a cell: the rates a council looks up (the text diet, the user, 30 September); the rest is in the ⓘ
  const rows = [
    { price: "Discount's resale cost", by: 'New-car sales', to: 'Used-car business', when: 'At sale',
      rate: `${nf(100 * pr.p1_low, 0)}–${nf(100 * pr.p1_high, 0)} cents per euro`,
      year: `${eurM(pr.p1_book_low, 0)}–${eurM(pr.p1_book_high, 0)}` },
    { price: "Market level's price", by: 'Residual setter', to: 'Holder at return', when: 'At signing',
      rate: `${pc(pr.p2_option_pct, 2)} of residual, option contracts`, year: eurM(pr.p2_tail_book_eur_m), note: 'buy-back tail' },
    { price: "Pricer's band", by: 'Used-car pricer', to: '–', when: 'At each price',
      rate: `±${nf(pr.band_avg_pct, 0)}% on average`, year: 'No charge' },
  ]
  return (
    <Card className="span-7" about="Three internal prices, charged at sale"
      title="Internal prices" sub="Rates in force" layers={['group']}
      info={{
        serves: 'making each business pay, at its decision, for what that decision costs the others (the Vehicle ' +
          'Value Council owns the prices).',
        detail: <>The discount's resale cost applies to cars the group takes back: {eurMraw(p1.charge_low)}–
          {eurMraw(p1.charge_high)} on the prototype's {nf(p1.cars)} fleet leases. The level's price is{' '}
          {pc(pr.p2_option_pct, 2)} of the residual where the customer holds the option ({eur(pr.p2_option_eur)} on a
          48-month contract); on the buy-back book, {eurM(pr.p2_tail_book_eur_m)} a year holds the tail, and +
          {nf(pr.p2_cold_pts, 2)} points ({eurM(pr.p2_cold_book_eur_m)} that year) when the level starts cold. The
          band is tied to the engine's: {nf(tc[1].cap, 1)}% at {tc[1].from}–{tc[1].to} years, {nf(tc[4].cap, 1)}% at{' '}
          {tc[4].from}+ years.</>,
        caveat: 'internal prices move costs between businesses; they add no cost to the group. The first is a range ' +
          'until the pilot calibrates it; our end of it is an upper bound.',
      }}>
      <div className="twin prices">
        <table>
          <caption className="sr">The three internal prices: who pays, who is paid, when, the rate and the euros a year</caption>
          <thead><tr><th scope="col">Price</th><th scope="col">Paid by</th><th scope="col">Paid to</th>
            <th scope="col">When</th><th scope="col">Rate</th><th scope="col" className="n">A year</th></tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.price}>
                <th scope="row">{r.price}</th><td>{r.by}</td><td>{r.to}</td><td>{r.when}</td>
                <td>{r.rate}</td><td className="n"><span className="nowrap">{r.year}</span>{'note' in r && `, ${r.note}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
