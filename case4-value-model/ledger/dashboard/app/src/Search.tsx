import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import * as Popover from '@radix-ui/react-popover'
import type { CarRef, Source } from './data'
import { cap, nf } from './format'
import { useCar } from './Drawer'
import { BodyIcon } from './icons'

// The tool pass, part 6: find a car, and each source's as-of date, both in the header.
// Find a car by its number or its make and model, across every car whose record the page holds (the queues' cars and
// the showcase cars); a result opens its record. The
// export carries no VIN, by design, so the car number is the key.

const WHERE: Record<CarRef['in'][number], string> = {
  claims: 'claims queue', upgrade: 'upgrade queue', incoming: 'incoming stock', desk: 'pricing desk',
}
const SHOW = 8

// digits: car numbers that start with them, the shortest (an exact number) first; anything else: make and model
export function find(index: CarRef[], q: string) {
  const s = q.trim().toLowerCase().replace(/\s+/g, ' ')
  if (!s) return []
  if (/^\d+$/.test(s)) return index.filter(r => String(r.car).startsWith(s))
    .sort((a, b) => String(a.car).length - String(b.car).length || a.car - b.car)
  return index.filter(r => `${r.make} ${r.model}`.includes(s))
    .sort((a, b) => a.make.localeCompare(b.make) || a.model.localeCompare(b.model) || a.car - b.car)
}

export function CarSearch({ index }: { index: CarRef[] }) {
  const { open } = useCar()
  const [q, setQ] = useState('')
  const [shown, setShown] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const id = useId()
  const hits = useMemo(() => find(index, q), [index, q])
  const on = shown && q.trim() !== ''
  // focus goes back to the box first, so it returns there when the record closes
  const go = (car: number) => { input.current?.focus(); setShown(false); open(car) }
  const keys = (e: KeyboardEvent) => {
    const items = [...(box.current?.querySelectorAll<HTMLButtonElement>('.hit') ?? [])]
    const i = items.indexOf(document.activeElement as HTMLButtonElement)
    if (e.key === 'ArrowDown' && items.length) { e.preventDefault(); setShown(true); (items[i + 1] ?? items[0]).focus() }
    else if (e.key === 'ArrowUp' && i >= 0) { e.preventDefault(); (i === 0 ? input.current : items[i - 1])?.focus() }
    else if (e.key === 'Escape' && on) { e.stopPropagation(); setShown(false); input.current?.focus() }
    else if (e.key === 'Enter' && document.activeElement === input.current && hits.length) { e.preventDefault(); go(hits[0].car) }
  }
  return (
    <div className="search" ref={box} onKeyDown={keys}
      onBlur={e => { if (!box.current?.contains(e.relatedTarget as Node)) setShown(false) }}>
      <input ref={input} type="search" value={q} placeholder="Find a car: number or model" aria-controls={id}
        aria-label="Find a car by its number or model" onFocus={() => setShown(true)}
        onChange={e => { setQ(e.target.value); setShown(true) }} />
      {on && <div className="search-pop" id={id} role="region" aria-label="Cars found">
        <p className="sub" aria-live="polite">{hits.length
          ? `${nf(hits.length)} of the ${nf(index.length)} cars${hits.length > SHOW ? `; the first ${SHOW}, type more to narrow` : ''}`
          : `No car matches. The search covers the ${nf(index.length)} cars whose record this page holds (every car ` +
            'in the queues, and the showcase cars), by number or model; no VIN leaves the ledger.'}</p>
        {hits.length > 0 && <ul>{hits.slice(0, SHOW).map(r => <li key={r.car}>
          <button type="button" className="hit" onClick={() => go(r.car)} aria-label={`Car ${r.car}, ${cap(r.make)} ${r.model}: open its record`}>
            <span><BodyIcon body={r.body} /><b>{r.car}</b> {cap(r.make)} {r.model}</span>
            <span className="sub">{r.in.length ? r.in.map(w => WHERE[w]).join(', ') : 'in no queue today'}</span>
          </button></li>)}</ul>}
      </div>}
    </div>
  )
}

// each source's as-of date: its latest event and the day the ledger last learnt something from it
export function SourceDates({ sources, asOf }: { sources: Source[]; asOf: string }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="text-btn">Each source's date</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="pop xwide" sideOffset={6} collisionPadding={16} align="start">
          <p>Every event carries two dates: when it happened and when the ledger learnt it. The prototype's today is the
            last month of marks, {asOf}; sources read later show here.</p>
          <div className="twin">
            <table>
              <caption className="sr">Each source's latest event and the day the ledger last learnt from it</caption>
              <thead><tr><th scope="col">Source</th><th scope="col">What it holds</th><th scope="col">Real or synthetic</th>
                <th scope="col" className="n">Records</th><th scope="col">Latest event</th><th scope="col">Last learnt</th></tr></thead>
              <tbody>{sources.map(s => <tr key={s.source}>
                <td>{s.name}<span className="sub">{s.views}</span></td><td>{s.holds}</td><td>{s.kind}</td>
                <td className="n">{nf(s.records)}</td><td className="nowrap">{s.happened}</td>
                <td className="nowrap">{s.learnt}</td></tr>)}</tbody>
            </table>
          </div>
          <Popover.Arrow className="pop-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
