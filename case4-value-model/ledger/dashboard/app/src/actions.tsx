import { createContext, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import type { CarEvent } from './Drawer'

// Actions on the work queues, simulated in this page (the tool pass, part 4): a person's decision is logged, shown on
// the row with an undo, and appended to the car's record as an event dated the prototype's today. Nothing leaves the
// page, and a reload clears the log.

export type QueueId = 'claims' | 'upgrade' | 'incoming' | 'desk'
export type Act = {
  key: number
  queue: QueueId
  row: string            // the row's id in its queue: a claim id, or a car id
  car: number | null     // the car whose record the action joins (an unlinked claim has none)
  what: string           // the event's name on the record; its first word places it in a lane
  detail: string
  eur: number | null
  inside?: boolean | null  // a logged price: inside the tied band, outside it, or a thin slice (no band applies)
}
type Ctx = {
  today: string
  acts: Act[]
  log: (a: Omit<Act, 'key'>) => void
  undo: (key: number) => void
  last: (q: QueueId, row: string) => Act | undefined
}
const ActCtx = createContext<Ctx>({ today: '', acts: [], log: () => {}, undo: () => {}, last: () => undefined })
export const useActions = () => useContext(ActCtx)

export function ActionsProvider({ today, children }: { today: string; children: ReactNode }) {
  const [acts, setActs] = useState<Act[]>([])
  const next = useRef(1)
  const ctx = useMemo<Ctx>(() => ({
    today, acts,
    log: a => setActs(xs => [...xs, { ...a, key: next.current++ }]),
    undo: key => setActs(xs => xs.filter(x => x.key !== key)),
    last: (q, row) => [...acts].reverse().find(x => x.queue === q && x.row === row),
  }), [today, acts])
  return <ActCtx.Provider value={ctx}>{children}</ActCtx.Provider>
}

// an action as an event on the car's record: it happened, and the group learnt it, today
export const asEvent = (a: Act, today: string): CarEvent =>
  [today, today, a.what, 'this page', a.eur, 'simulated', a.detail]

// the CFO's reading: logged first proposals inside the tied band, of those the band applies to
export function alignment(acts: Act[]) {
  const desk = acts.filter(a => a.queue === 'desk')
  const inside = desk.filter(a => a.inside === true).length, outside = desk.filter(a => a.inside === false).length
  return { inside, outside, thin: desk.length - inside - outside }
}
