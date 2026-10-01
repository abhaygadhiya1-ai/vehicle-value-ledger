import { MDI } from './mdi'
import { CARBON } from './carbon'

// The tool pass, part 7: an icon per event type on the car's record (its timeline and its table). A claim held or in
// review is a status, not an event type: it keeps the page's status shapes (a square, a triangle).
const EVENT: [test: RegExp, icon: string][] = [
  [/^order$/, 'document--signed'], [/^order log$/, 'recently-viewed'], [/^registration$/, 'identification'],
  [/^list price$/, 'tag'], [/^dealer transfer$/, 'arrows--horizontal'], [/^claim$/, 'receipt'],
  [/^claim decision$/, 'list--checked'], [/^finance start$/, 'finance'], [/^first keeper$/, 'user'],
  [/^keeper read$/, 'search'], [/^tradein$/, 'repeat'], [/^keeper handover$/, 'password'], [/^came to market$/, 'undo'],
  [/^resale$/, 'currency--euro'],
  // actions logged on this page (simulated)
  [/^claim paid$/, 'checkmark'], [/^claim kept on hold$/, 'locked'], [/^claim query sent/, 'email'], [/^timing sent/, 'send'],
  [/^partner: upgraded$/, 'upgrade'], [/^partner: call back later$/, 'phone--outgoing'], [/^partner: declined$/, 'close--outline'],
  [/^routed:/, 'direction--right--01'], [/^price logged/, 'edit'],
]
export const STATUS_EVENT = /^claim (hold|review)$/
export const eventIcon = (event: string) => EVENT.find(([t]) => t.test(event))?.[1]

// an icon as an image for the timeline (ECharts draws it), on a disc: filled when the group knew the event by the date,
// outlined when it had happened but was not yet learnt, ringed with dashes when a person logged it on this page
export function iconImage(name: string, fill: string, disc: string, ring: string, dashed: boolean) {
  const r = `<circle cx="12" cy="12" r="11" fill="${disc}" stroke="${ring}" stroke-width="1.5"` +
    (dashed ? ' stroke-dasharray="3 2"/>' : '/>')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">${r}` +
    `<g transform="translate(5 5) scale(.4375)" fill="${fill}">${CARBON[name]}</g></svg>`
  return 'image://data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

// a Carbon icon inline, in the text colour (the shapes are our own constants, verbatim from Carbon's repository)
export function Icon({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  return (
    <svg className={'ic-ev ' + (className ?? '')} width={size} height={size} viewBox="0 0 32 32" fill="currentColor"
      aria-hidden="true" dangerouslySetInnerHTML={{ __html: CARBON[name] }} />
  )
}

// ------------------------------------------------------------------ body types: Material Design Icons, facing right
// RDW's own classes, named as RDW names them (its "MPV" holds most SUVs and crossovers); any other class, MDI's car.
const BODY: Record<string, string> = {
  hatchback: 'car-hatchback', estate: 'car-estate', MPV: 'van-passenger', saloon: 'car-side', camper: 'rv-truck',
  'coupé': 'car-sports', convertible: 'car-convertible',
}
export function BodyIcon({ body, size = 24 }: { body: string; size?: number }) {
  const [box, d] = MDI[BODY[body] ?? 'car']
  return (
    <svg className="body-ic" width={size} height={size / 2} viewBox={box} role="img" aria-label={body}>
      <title>{body}</title><path d={d} fill="currentColor" />
    </svg>
  )
}
