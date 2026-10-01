import { createContext, useContext, useId, useState, type ReactNode } from 'react'
import { cap, eur, eurK, nf, oneIn, pc } from './format'
import * as Popover from '@radix-ui/react-popover'
import { BodyIcon, Icon } from './icons'
import { Roll } from './roll'
import { useAutoAnimate } from '@formkit/auto-animate/react'
import { glide } from './glide'

// ------------------------------------------------------------------ badges: which world a number comes from
export type Layer = 'group' | 'proto' | 'demo'
// the view's own layer, which its band names; cards leave it out of their badges
export const ViewLayer = createContext<Layer | null>(null)
const BADGE: Record<Layer, [string, string]> = {
  group: ['badge group', 'Group figure'],
  proto: ['badge proto', 'Prototype: synthetic world'],
  demo: ['badge demo', 'Demonstration'],
}
export const Badge = ({ layer, short }: { layer: Layer; short?: boolean }) =>
  <span className={BADGE[layer][0]}>{short && layer === 'proto' ? 'Prototype' : BADGE[layer][1]}</span>

// ------------------------------------------------------------------ status: a shape and a label, never colour alone
const ICON = {
  crit: <rect x="1.5" y="1.5" width="9" height="9" rx="1" />,
  warn: <path d="M6 1 11.2 10.5H.8Z" />,
  ok: <circle cx="6" cy="6" r="4.75" />,
}
export const Status = ({ kind, children }: { kind: keyof typeof ICON; children: ReactNode }) =>
  <span className={'st ' + kind}><svg className="ic" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
    {ICON[kind]}</svg>{children}</span>

// ------------------------------------------------------------------ the ⓘ: what a panel serves, its source, its caveat
// detail: what a table's cells leave out (the text diet: one short line a cell on the page)
export type Info = { serves: ReactNode; source?: ReactNode; detail?: ReactNode; caveat?: ReactNode }
export function InfoButton({ info, about }: { info: Info; about: string }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="icon-btn" aria-label={`Why and source: ${about}`}>
        <Icon name="information" size={16} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="pop" sideOffset={6} collisionPadding={16} align="end">
          <p><b>Serves:</b> {info.serves}</p>
          {info.source && <p><b>Source:</b> {info.source}</p>}
          {info.detail && <p><b>Detail:</b> {info.detail}</p>}
          {info.caveat && <p><b>Caveat:</b> {info.caveat}</p>}
          <Popover.Arrow className="pop-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

// ------------------------------------------------------------------ a chart's table twin
export type Twin = { cols: string[]; rows: ReactNode[][]; num?: boolean[]; tall?: boolean }
export function TwinTable({ twin, caption }: { twin: Twin; caption: string }) {
  return (
    <div className={'twin' + (twin.tall ? ' tall' : '')}>
      <table>
        <caption className="sr">{caption}</caption>
        <thead><tr>{twin.cols.map((c, i) => <th key={i} scope="col" className={twin.num?.[i] ? 'n' : ''}>{c}</th>)}</tr></thead>
        <tbody>{twin.rows.map((r, j) => <tr key={j}>{r.map((c, i) =>
          <td key={i} className={twin.num?.[i] ? 'n' : ''}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

// ------------------------------------------------------------------ the card: a finding, one chart, one action line
type CardProps = {
  title: ReactNode         // a label, what the card shows (SAP Fiori's "Revenue by Quarter"): no figures, no sentence
  sub?: ReactNode          // the card's figure and qualifiers, one short line under the label (the AI look, part 1)
  about: string            // the title in words, for labels
  layers: Layer[]
  info: Info
  twin?: Twin
  action?: ReactNode
  tools?: ReactNode        // controls beside the title (a toggle)
  className?: string
  children: ReactNode
}
export function Card({ title, sub, about, layers, info, twin, action, tools, className, children }: CardProps) {
  const [asTable, setAsTable] = useState(false)
  const id = useId()
  const view = useContext(ViewLayer), shown = layers.filter(l => l !== view)
  return (
    <section className={'card ' + (className ?? '')} aria-labelledby={id}>
      <header className="card-head">
        <div className="card-title">
          <h3 id={id}>{title}</h3>
          {sub && <p className="card-sub">{sub}</p>}
          {shown.length > 0 && <span className="card-badges">{shown.map(l => <Badge key={l} layer={l} short />)}</span>}
        </div>
        <div className="card-tools">
          {tools}
          {twin &&<button type="button" className="icon-btn" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}
            aria-label={`Show as a table: ${about}`} title="Show as a table">
            <Icon name="table" size={16} />
          </button>}
          <InfoButton info={info} about={about} />
        </div>
      </header>
      <div className="card-body">{asTable && twin ? <TwinTable twin={twin} caption={about} /> : children}</div>
      {action && <p className="action">{action}</p>}
    </section>
  )
}

// ------------------------------------------------------------------ the band: a view's title and its answer in tiles
// role: whose day the view opens on (the tool pass: each view is one team's tool)
// compact: a team view's header (the AI look, part 6; SAP Fiori's dynamic page, whose worklists carry key figures in the
// title area): the title row, then each figure as a label before its value; the CFO's and the office's views keep navy
const Compact = createContext(false)
export function Band({ title, role, info, badge, compact = false, children }: { title: string; role?: string; info: Info
  badge?: Layer; compact?: boolean; children: ReactNode }) {
  const view = useContext(ViewLayer), shown = badge ?? view   // the view's layer, from VIEWS
  const tag = shown && <span className="tiles-badge"><Badge layer={shown} /></span>
  return (
    <div className={'band' + (compact ? ' compact' : '')}>
      <div className="wrap">
        <div className="band-head">
          {compact && <span className="band-sw" aria-hidden="true" />}{/* on navy it read as an empty checkbox */}
          <h2>{title}</h2>
          <InfoButton about={title} info={info} />
          {role && <span className="band-role">{role}</span>}
          {compact && tag}
        </div>
        <Compact.Provider value={compact}>
          <div className="tiles">
            {children}
            {!compact && tag}
          </div>
        </Compact.Provider>
      </div>
    </div>
  )
}

// note: in a compact band, what qualifies the value (its euros, its age), after it; the label says what it counts
type TileProps = { v: ReactNode; l: ReactNode; note?: ReactNode; hero?: boolean; status?: ReactNode; onClick?: () => void }
export function Tile({ v, l, note, hero, status, onClick }: TileProps) {
  const tv = <div className="tv">{typeof v === 'string' ? <Roll text={v} /> : v}</div>
  const body = useContext(Compact)
    ? <><div className="tl">{l}</div><div className="tvr">{tv}{note && <span className="tn">{note}</span>}{status}</div></>
    : <>{tv}<div className="tl">{l}</div>{status}</>
  return onClick
    ? <button type="button" className={'tile' + (hero ? ' hero' : '')} onClick={onClick}>{body}</button>
    : <div className={'tile' + (hero ? ' hero' : '')}>{body}</div>
}

// ------------------------------------------------------------------ a work queue: sortable, 10 rows, then all
export type Col<R> = { h: string; get: (r: R) => ReactNode; sort?: (r: R) => string | number; num?: boolean; cls?: string }
type QueueProps<R> = { rows: R[]; rowKey: (r: R) => string | number; cols: Col<R>[]; label: string; first: number;
  dir?: 1 | -1; limit?: number;
  empty?: ReactNode; all?: boolean; setAll?: (b: boolean) => void; tall?: boolean }
// `all` and `setAll` given: the parent shows the "Show all" control (in the card's head); otherwise a foot row does
export function Queue<R>({ rows, rowKey, cols, label, first, dir: dir0 = -1, limit = 10, empty, tall, ...ctl }: QueueProps<R>) {
  const [body] = useAutoAnimate<HTMLTableSectionElement>(glide)   // rows glide on a sort (glide.ts)
  const [key, setKey] = useState(first)
  const [dir, setDir] = useState<1 | -1>(dir0)
  const [own, setOwn] = useState(false)
  const all = ctl.all ?? own, setAll = ctl.setAll ?? setOwn
  const by = cols[key].sort!
  const sorted = [...rows].sort((a, b) => { const x = by(a), y = by(b); return (x > y ? 1 : x < y ? -1 : 0) * dir })
  const shown = all ? sorted : sorted.slice(0, limit)
  const sortBy = (i: number) => {
    if (i === key) setDir(dir === 1 ? -1 : 1)
    else { setKey(i); setDir(cols[i].num ? -1 : 1) }
  }
  return (
    <div className={'queue' + (tall ? ' tall' : '')}>
      <div className="qwrap">
        <table>
          <caption className="sr">{label}</caption>
          <thead><tr>{cols.map((c, i) => (
            <th key={c.h} scope="col" className={c.num ? 'n' : ''}
              aria-sort={i === key ? (dir === 1 ? 'ascending' : 'descending') : c.sort ? 'none' : undefined}>
              {c.sort ? <button type="button" className="sort" onClick={() => sortBy(i)}>{c.h}
                <span className="si" aria-hidden="true">{i === key ? (dir === 1 ? '↑' : '↓') : '↕'}</span></button> : c.h}
            </th>))}</tr></thead>
          <tbody ref={body}>{shown.map(r => <tr key={rowKey(r)}>{cols.map(c =>
            <td key={c.h} className={(c.num ? 'n ' : '') + (c.cls ?? '')}>{c.get(r)}</td>)}</tr>)}</tbody>
        </table>
        {rows.length === 0 && <p className="q-empty">{empty}</p>}
      </div>
      {rows.length > limit && !ctl.setAll && (
        <div className="q-foot">
          <span>{all ? rows.length : Math.min(limit, rows.length)} of {rows.length} rows</span>
          <button type="button" className="text-btn" onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? `Show the first ${limit}` : `Show all ${rows.length}`}</button>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ queue cells: a value and its band, a chance
// A car's value as its 80% band, the mark a thin tick (Kale et al.: means bias a little, so keep the point thin), on a
// common ±S scale for the whole queue, so bands compare row to row.
export type Banded = { mark: number; low: number; high: number }
export const scaleOf = (rows: Banded[]) =>
  Math.max(0.1, Math.ceil(10 * Math.max(...rows.map(r => Math.max(r.high / r.mark - 1, 1 - r.low / r.mark)))) / 10)
export function BandBar({ r, S }: { r: Banded; S: number }) {
  const w = 96, h = 12, x = (v: number) => Math.max(0, Math.min(w, w / 2 + (w / 2) * ((v / r.mark) - 1) / S))
  return (
    <svg className="vb" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img"
      aria-label={`80% band ${eur(r.low)} to ${eur(r.high)}`}>
      <line x1="0" x2={w} y1={h / 2} y2={h / 2} className="vb-axis" />
      <rect x={x(r.low).toFixed(1)} y="2" width={(x(r.high) - x(r.low)).toFixed(1)} height={h - 4} rx="2" className="vb-band" />
      <rect x={(x(r.mark) - 1).toFixed(1)} y="0" width="2" height={h} className="vb-tick" />
    </svg>
  )
}
export const ValueCell = ({ r, S }: { r: Banded; S: number }) => <>
  <span className="nowrap vcell"><BandBar r={r} S={S} />{eur(r.mark)}</span>
  <span className="sub nowrap">{eurK(r.low)}–{eurK(r.high)}</span></>
type Chance = { p3: number; p3_low: number; p3_high: number }
export const ChanceCell = ({ r }: { r: Chance }) => <>
  <span className="nowrap">{pc(r.p3)} <span className="muted">({oneIn(r.p3)})</span></span>
  <span className="sub nowrap" title="Sampling error in the engine's measurements, not how sure we are about this car">
    {nf(r.p3_low, 1)}–{nf(r.p3_high, 1)}%</span></>
// noThin: where the row's type chip already says "Little history" (the pricing desk)
export const ModelCell = ({ r, thinCars, noThin }: { r: { make: string; model: string; body?: string; thin?: boolean }
  thinCars: number; noThin?: boolean }) => <>
  <span className="nowrap">{r.body && <BodyIcon body={r.body} />}{cap(r.make)} {r.model}</span>
  {r.thin && !noThin && <span className="chip" title={`Fewer than ${nf(thinCars)} cars of this model in the book: a wider band and a person's sign-off`}>
    Little history</span>}</>

// ------------------------------------------------------------------ a row's reason type, from its queue's short fixed list
// (the tool pass, part 5): a filled tag, apart from the outlined status chips; its meaning on hover and in the card's ⓘ
export const TypeChip = ({ type, list, inline }: { type: string; list: [string, string][]; inline?: boolean }) =>
  <span className={'chip type' + (inline ? ' inl' : '')} title={list.find(x => x[0] === type)?.[1]}>{type}</span>
export const typeList = (list: [string, string][]) => list.map(([t, m]) => `${t}: ${m}`).join('. ')
