// Number formats, the same as the verified page's: en-GB grouping, a true minus sign, "–" for a missing value.

const MINUS = '−'
export const nf = (x: number | null | undefined, d = 0) => x == null || isNaN(x) ? '–'
  : Number(x).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d }).replace('-', MINUS)
export const eur = (x: number | null | undefined, d = 0) => x == null ? '–' : (x < 0 ? MINUS + '€' : '€') + nf(Math.abs(x), d)
export const eurM = (m: number | null | undefined, d = 1) => m == null ? '–' : eur(m, d) + 'm'    // from millions
export const eurMraw = (x: number | null | undefined, d = 1) => x == null ? '–' : eurM(x / 1e6, d)  // from euros
export const eurK = (x: number) => '€' + nf(x / 1000, x >= 100000 ? 0 : 1) + 'k'
// a chance as a frequency beside the percentage (Fernandes et al.: frequency framing)
export const oneIn = (p: number) => p > 0 ? '1 in ' + nf(Math.round(100 / p)) : '–'
export const pc = (x: number | null | undefined, d = 1) => x == null ? '–' : nf(x, d) + '%'
export const signed = (x: number, d = 1) => (x > 0 ? '+' : x < 0 ? MINUS : '') + pc(Math.abs(x), d)
// a make or reason as a name: each word capitalised, DS in capitals (as the verified page)
export const cap = (s: string) => s.split(' ').map(w => w === 'ds' ? 'DS' : w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
// a reason as a phrase: sentence case
export const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
export const monthName = (m: string) => new Date(m + '-01T00:00:00Z')
  .toLocaleString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' })
