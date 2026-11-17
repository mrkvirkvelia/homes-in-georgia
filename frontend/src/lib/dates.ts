// Pure calendar-date math on y/m/d integers. No Date objects: `new Date('2024-03-01')` is UTC midnight and its local
// getters give 29 Feb west of Greenwich, and Date's own month overflow turns 31 Aug + 6 months into 3 March.
// One rule for every "+N months" in the CRM: keep the day, clamp to the target month's end (31 Aug + 6 → 28/29 Feb).

export interface Ymd { y: number; m: number; d: number } // m is 1..12

const pad = (n: number, w = 2) => String(n).padStart(w, '0');
const leap = (y: number) => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
export const daysInMonth = (y: number, m: number) => [31, leap(y) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];

/** 'yyyy-mm-dd' (a longer ISO string is cut to its date) → Ymd, or null if it is not a real calendar date. */
export function parseIsoDate(iso: string): Ymd | null {
  const r = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  if (!r) return null;
  const y = +r[1], m = +r[2], d = +r[3];
  return m >= 1 && m <= 12 && d >= 1 && d <= daysInMonth(y, m) ? { y, m, d } : null;
}

export const isoDate = ({ y, m, d }: Ymd) => `${pad(y, 4)}-${pad(m)}-${pad(d)}`;
export const ruDate = ({ y, m, d }: Ymd) => `${pad(d)}.${pad(m)}.${pad(y, 4)}`;

/** Date + n months (n may be negative), day clamped to the end of the target month. */
export function addMonths(a: Ymd, n: number): Ymd {
  const idx = a.y * 12 + (a.m - 1) + Math.trunc(n);
  const y = Math.floor(idx / 12), m = idx - y * 12 + 1;
  return { y, m, d: Math.min(a.d, daysInMonth(y, m)) };
}

/** Whole months from a to b: the largest k with addMonths(a, k) <= b (so 31 Aug → 28 Feb is 6 months). */
export function wholeMonths(a: Ymd, b: Ymd): number {
  let k = (b.y - a.y) * 12 + (b.m - a.m);
  const cmp = (x: Ymd, z: Ymd) => (x.y - z.y) || (x.m - z.m) || (x.d - z.d);
  while (k > 0 && cmp(addMonths(a, k), b) > 0) k -= 1;
  return k;
}

/** Today's local calendar date. */
export function todayYmd(now = new Date()): Ymd { return { y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() }; }
