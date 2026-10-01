import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import * as Popover from '@radix-ui/react-popover'
import type { Dash } from './data'
import { useTokens } from './tokens'
import { signed } from './format'
import { Badge } from './ui'
import { VIEWS, type ViewId } from './views'
import { Management } from './views/Management'
import { NewCar } from './views/NewCar'
import { Finance } from './views/Finance'
import { Resale } from './views/Resale'
import { Programme } from './views/Programme'
import { CarProvider } from './Drawer'
import { ActionsProvider } from './actions'
import { CarSearch, SourceDates } from './Search'
import { ViewLayer } from './ui'
import { ThemeToggle } from './theme'

const layerOf = (id: ViewId) => VIEWS.find(v => v.id === id)!.layer

const fromHash = (): ViewId => {
  const h = location.hash.slice(1)
  return VIEWS.some(v => v.id === h) ? h as ViewId : 'mgmt'
}

export function App({ dash }: { dash: Dash }) {
  const t = useTokens()
  const [view, setView] = useState<ViewId>(fromHash)
  const [level, setLevel] = useState(0)            // the market level's move, in %: every car at once
  const passed = dash.checks.filter(c => c[1]).length

  const open = (v: ViewId) => { setView(v); window.scrollTo({ top: 0 }) }
  // the open tab's line (styles.css .tab-ink): placed under the open tab, sliding when another opens
  const list = useRef<HTMLDivElement>(null)
  const [ink, setInk] = useState<{ x: number; w: number; off?: boolean } | null>(null)
  useLayoutEffect(() => {
    const el = list.current!
    const place = () => {
      const a = el.querySelector<HTMLElement>('.tab[data-state="active"]')
      setInk(p => a ? { x: a.offsetLeft, w: a.offsetWidth } : p && { ...p, off: true })   // the office: fade in place
    }
    place()
    const ro = new ResizeObserver(place)
    ro.observe(el)
    return () => ro.disconnect()
  }, [view])
  useEffect(() => {
    try { history.replaceState(null, '', location.search + '#' + view) } catch { /* file:// in some browsers */ }
    // at phone width the tab row scrolls sideways: keep the open view's tab in sight
    document.querySelector('.tab[data-state="active"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [view])

  return (
    <ActionsProvider today={dash.proto.as_of}>
    <CarProvider dash={dash} t={t}>
      <header className="top">
        <div className="wrap top-row">
          <div className="top-title">
            <h1>Vehicle value ledger</h1>
            <CarSearch index={dash.proto.car_index} />
          </div>
            <div className="legend">
              <span className="meta">Prototype as of {dash.proto.as_of}, built {dash.built}, {passed} of {dash.checks.length} export checks pass</span>
              <Badge layer="group" /><Badge layer="proto" />
              <Popover.Root>
                <Popover.Trigger className="text-btn">What the badges mean</Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content className="pop" sideOffset={6} collisionPadding={16} align="start">
                    <p><Badge layer="group" /> the programme's numbers: the register and the value-at-risk workbook
                      (Stellantis FY2025 as a same-scale proxy).</p>
                    <p><Badge layer="proto" /> real Dutch cars, dates and price index; synthetic claims, contracts and
                      labels. Never the group's totals.</p>
                    <Popover.Arrow className="pop-arrow" />
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
              <SourceDates sources={dash.proto.sources} asOf={dash.proto.as_of} />
            </div>
          <div className="level">
            <label htmlFor="lvl">Market level move</label>
            <input id="lvl" type="range" min={-30} max={30} step={1} value={level}
              style={{ '--p': (level + 30) / 60 } as CSSProperties}
              aria-valuetext={`${signed(level, 0)}: every car's value moves at once`}
              onChange={e => setLevel(Number(e.target.value))} />
            <output htmlFor="lvl">{signed(level, 0)}</output>
            <button type="button" className="text-btn" disabled={level === 0} onClick={() => setLevel(0)}>Reset</button>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <Tabs.Root value={view} onValueChange={v => setView(v as ViewId)} activationMode="automatic">
        <nav className="tabs-bar" aria-label="Views">
          <div className="wrap tabs-row">
            <Tabs.List ref={list} className="tabs" aria-label="The four team views">
              {VIEWS.filter(v => v.id !== 'programme').map(v => (
                <Tabs.Trigger key={v.id} value={v.id} className="tab" style={{ '--acc': v.acc } as CSSProperties}>
                  <span className="sw" aria-hidden="true" />{v.name}
                </Tabs.Trigger>
              ))}
              <span aria-hidden="true" className={'tab-ink' + (ink && !ink.off ? '' : ' off')} style={ink ? {
                transform: `translateX(${ink.x}px)`, width: ink.w, '--acc': VIEWS.find(v => v.id === view)!.acc,
              } as CSSProperties : undefined} />
            </Tabs.List>
            <button type="button" className="office-btn" aria-current={view === 'programme' ? 'page' : undefined}
              onClick={() => open('programme')}>
              Programme office <span className="apart">apart from the tool</span>
            </button>
          </div>
        </nav>
        <main>
          <Tabs.Content value="mgmt" className="view" style={{ '--acc': 'var(--acc-mgmt)' } as CSSProperties}>
            <ViewLayer.Provider value={layerOf('mgmt')}><Management dash={dash} t={t} level={level} open={open} /></ViewLayer.Provider>
          </Tabs.Content>
          <Tabs.Content value="oem" className="view" style={{ '--acc': 'var(--acc-oem)' } as CSSProperties}>
            <ViewLayer.Provider value={layerOf('oem')}><NewCar dash={dash} t={t} open={open} /></ViewLayer.Provider>
          </Tabs.Content>
          <Tabs.Content value="fin" className="view" style={{ '--acc': 'var(--acc-fin)' } as CSSProperties}>
            <ViewLayer.Provider value={layerOf('fin')}><Finance dash={dash} t={t} level={level} open={open} /></ViewLayer.Provider>
          </Tabs.Content>
          <Tabs.Content value="resale" className="view" style={{ '--acc': 'var(--acc-res)' } as CSSProperties}>
            <ViewLayer.Provider value={layerOf('resale')}><Resale dash={dash} t={t} open={open} /></ViewLayer.Provider>
          </Tabs.Content>
          <Tabs.Content value="programme" className="view" style={{ '--acc': 'var(--acc-prog)' } as CSSProperties}>
            <ViewLayer.Provider value={layerOf('programme')}><Programme dash={dash} t={t} open={open} /></ViewLayer.Provider>
          </Tabs.Content>
        </main>
        <footer className="wrap foot">
          <p>Independent student work for a case competition, not affiliated with or endorsed by Capgemini or
            Stellantis. Stellantis is used as a public same-scale proxy for the case's anonymous group.{' '}
            <a href="THIRD_PARTY_NOTICES.txt">Third-party licences</a></p>
        </footer>
      </Tabs.Root>
    </CarProvider>
    </ActionsProvider>
  )
}
