import { useEffect, useRef } from 'react'
import { isDark } from './theme'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, SankeyChart, ScatterChart } from 'echarts/charts'
import { AriaComponent, DataZoomComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent }
  from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

// SVG, not canvas: chart text stays in the page, so the look checks can read its fonts, sizes and contrast.
echarts.use([BarChart, LineChart, SankeyChart, ScatterChart, AriaComponent, DataZoomComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent,
  TooltipComponent, SVGRenderer])

export type ChartOption = echarts.EChartsCoreOption
export type ChartApi = echarts.ECharts

type Props = {
  option: ChartOption
  height: number
  label: string
  onReady?: (c: ChartApi) => void
}

export function Chart({ option, height, label, onReady }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const chart = useRef<ChartApi | null>(null)

  useEffect(() => {
    const c = echarts.init(box.current!, null, { renderer: 'svg' })
    chart.current = c
    onReady?.(c)
    // resize only on a real change: the observer's first call (at once, same size) would cut the entry animation short
    const ro = new ResizeObserver(() => {
      const b = box.current
      if (b && (b.clientWidth !== c.getWidth() || b.clientHeight !== c.getHeight())) c.resize()
    })
    ro.observe(box.current!)
    return () => { ro.disconnect(); c.dispose(); chart.current = null }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  // a theme change redraws at once (no update animation), so the page's cross-fade shows the new colours (theme.tsx)
  const dark = useRef(isDark())
  useEffect(() => {
    const now = isDark()
    chart.current?.setOption(now === dark.current ? option : { ...option, animation: false })
    dark.current = now
  }, [option])

  return <div ref={box} className="echart" role="img" aria-label={label} style={{ height }} />
}
