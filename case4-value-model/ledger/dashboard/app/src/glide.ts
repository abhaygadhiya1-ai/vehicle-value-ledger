/*! Queue rows glide with AutoAnimate (https://auto-animate.formkit.com; the `@formkit/auto-animate` package, v0.10.0,
MIT); its licence, verbatim:

Copyright 2022 FormKit Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
*/
import type { AutoAnimationPlugin } from '@formkit/auto-animate'

// A queue's rows (after the tool pass, part 8): on a sort each row glides from where it was to where it goes (240 ms,
// Carbon's standard curve); on a filter or "Show all" a new row fades in; a row that leaves goes at once, since
// AutoAnimate lifts a leaving element out of the flow (position absolute) and a table row's cells then lose their
// columns. Only the transform and opacity move, so rows keep their 48 or 32 px. A plugin is not switched off by
// AutoAnimate under reduced motion, so it checks for itself. AutoAnimate passes the new place before the old one.
export const glide: AutoAnimationPlugin = (el, action, to, from) => {
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches
  const frames: Keyframe[] = action === 'add' ? [{ opacity: 0 }, { opacity: 1 }]
    : action === 'remain' && to && from
      ? [{ transform: `translate(${from.left - to.left}px, ${from.top - to.top}px)` }, { transform: 'none' }]
      : []
  return new KeyframeEffect(el, frames, { duration: still || action === 'remove' ? 0 : 240,
    easing: 'cubic-bezier(0.2, 0, 0.38, 0.9)' })
}
