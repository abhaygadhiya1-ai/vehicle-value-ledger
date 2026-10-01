/*! The rolling numbers are NumberFlow (https://number-flow.barvian.me; the `@number-flow/react` and `number-flow`
packages, v0.6.2, both under this licence); its licence, verbatim:

MIT License

Copyright (c) 2024 Maxwell Barvian

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
import NumberFlow from '@number-flow/react'

// A number that rolls to its new value when it changes (after the tool pass, part 7): the slider, a logged action. It
// takes the page's own formatted string, splits it into what comes before the number, the number and what comes after,
// and rolls the number with the same decimals and grouping; anything else (a range, a count with words between) shows
// as it is. NumberFlow respects reduced motion itself and reads as one labelled image to a screen reader.
const PARTS = /^([^\d]*?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?([^\d]*)$/
const EASE = 'cubic-bezier(0.05, 0.7, 0.1, 1)'   // Material 3's emphasized decelerate, as the tiles' arrival

export function Roll({ text }: { text: string }) {
  const m = PARTS.exec(text)
  if (!m) return <>{text}</>
  const [, pre, int, frac = '', post] = m
  const d = frac.length
  return (
    <span className="roll" data-value={text}>
      <NumberFlow value={Number(int.replace(/,/g, '') + (d ? '.' + frac : ''))} locales="en-GB"
        format={{ minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: !(int.length > 3 && !int.includes(',')) }}
        prefix={pre || undefined} suffix={post || undefined}
        spinTiming={{ duration: 600, easing: EASE }} transformTiming={{ duration: 600, easing: EASE }}
        opacityTiming={{ duration: 300, easing: 'ease-out' }} />
    </span>
  )
}
