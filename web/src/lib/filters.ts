// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Catalogue filters: the state lives in the URL query (every key below is a query param), so pages are shareable.
import { placeSearchText } from './places';
import { shortId } from './format';
import type { Item } from './types';

export const LIST_KEYS = ['beds', 'kind', 'deal', 'district', 'building', 'condition', 'amen', 'gearbox', 'fuel', 'body', 'heating'] as const;
export const RANGE_KEYS = ['price', 'area', 'year', 'mileage', 'floor', 'floors', 'ppsqm', 'deposit'] as const;
export const FLAG_KEYS = ['pets', 'excl', 'notfirst', 'notlast'] as const;
export const TEXT_KEYS = ['metro', 'term', 'tenants', 'seats', 'pickup'] as const;

export type Range = [number | null, number | null];
export type Filters =
  { q: string; sort: string }
  & Record<(typeof LIST_KEYS)[number], string[]>
  & Record<(typeof RANGE_KEYS)[number], Range>
  & Record<(typeof FLAG_KEYS)[number], boolean>
  & Record<(typeof TEXT_KEYS)[number], string>;

export type Params = Pick<URLSearchParams, 'get'>;

export function parseFilters(params: Params): Filters {
  const f = { q: params.get('q') || '', sort: params.get('sort') || 'new' } as Filters;
  TEXT_KEYS.forEach(k => { f[k] = params.get(k) || ''; });
  LIST_KEYS.forEach(k => { f[k] = (params.get(k) || '').split(',').filter(Boolean); });
  RANGE_KEYS.forEach(k => {
    const [a, b] = (params.get(k) || '').split('-').map(v => (v === '' || v == null ? null : +v));
    f[k] = [Number.isFinite(a) ? a : null, Number.isFinite(b) ? b : null];
  });
  FLAG_KEYS.forEach(k => { f[k] = params.get(k) === '1'; });
  return f;
}

export function filtersToParams(f: Filters, params = new URLSearchParams()): URLSearchParams {
  const set = (k: string, v: string) => (v ? params.set(k, v) : params.delete(k));
  set('q', f.q.trim());
  set('sort', f.sort === 'new' ? '' : f.sort);
  TEXT_KEYS.forEach(k => set(k, f[k]));
  LIST_KEYS.forEach(k => set(k, f[k].join(',')));
  RANGE_KEYS.forEach(k => set(k, f[k][0] == null && f[k][1] == null ? '' : `${f[k][0] ?? ''}-${f[k][1] ?? ''}`));
  FLAG_KEYS.forEach(k => set(k, f[k] ? '1' : ''));
  return params;
}

export function activeCount(f: Filters): number {
  return LIST_KEYS.reduce((n, k) => n + f[k].length, 0)
    + RANGE_KEYS.filter(k => f[k][0] != null || f[k][1] != null).length
    + FLAG_KEYS.filter(k => f[k]).length + TEXT_KEYS.filter(k => f[k]).length;
}

/** Lower-cased search text: listing ID ("o547672", "547672", the old "rent-547672"), address, place names in RU / EN / KA. */
export const searchText = (x: Item): string =>
  [x.id, x.legacy_id, shortId(x.id), shortId(x.legacy_id), x.title, x.headline, placeSearchText(x.district), placeSearchText(x.metro), x.pickup, x.kind, x.year, x.description]
    .filter(Boolean).join(' ').toLowerCase();

/** A listing plus its search text: what the filters work on (the home finder sends a slim subset of the fields). */
export type Row = Partial<Item> & { text: string };
export const toRow = (x: Item): Item & { text: string } => ({ ...x, text: searchText(x) });

const inRange = (v: number | undefined | null, [a, b]: Range = [null, null]) => (a == null || (v != null && v >= a)) && (b == null || (v != null && v <= b));

function termMatch(x: Row, term: string) {
  const m = x.months || [];
  if (!m.length) return false;
  if (term === 'short') return m.some(v => v <= 6);
  if (term === 'year') return m.includes(12);
  return m.some(v => v >= 24);
}
export const depositOf = (x: Pick<Item, 'deposit' | 'price' | 'price_usd'>) => (x.deposit && x.price && x.price_usd ? x.deposit * x.price_usd / x.price : null);

export function applyFilters<T extends Row>(items: T[], f: Filters, skip = ''): T[] {
  const words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(x =>
    (!words.length || words.every(w => x.text.includes(w)))
    && (skip === 'price' || inRange(x.price_usd, f.price))
    && (skip === 'area' || inRange(x.area, f.area))
    && (skip === 'year' || inRange(x.year, f.year))
    && (skip === 'mileage' || inRange(x.mileage, f.mileage))
    && (!f.deal.length || (!!x.deal && f.deal.includes(x.deal)))
    && (!f.gearbox.length || (!!x.gearbox && f.gearbox.includes(x.gearbox)))
    && (!f.fuel.length || (!!x.fuel && f.fuel.includes(x.fuel)))
    && (!f.body.length || (!!x.body && f.body.includes(x.body)))
    && (!f.beds.length || f.beds.some(b => (b === '4' ? (x.rooms ?? -1) >= 4 : x.rooms === +b)))
    && (!f.kind.length || (!!x.kind && f.kind.includes(x.kind)))
    && (skip === 'district' || !f.district.length || (!!x.district && f.district.includes(x.district)))
    && (!f.metro || x.metro === f.metro)
    && (!f.building.length || (!!x.building && f.building.includes(x.building)))
    && (!f.condition.length || (!!x.condition && f.condition.includes(x.condition)))
    && (!f.heating.length || (!!x.heating && f.heating.includes(x.heating)))
    && (!f.amen.length || f.amen.every(a => x.amenities?.includes(a)))
    && (!f.pets || x.pets === 'allowed' || x.pets === 'agreement')
    && (!f.term || termMatch(x, f.term))
    && (!f.excl || x.exclusive)
    && inRange(x.floor, f.floor)
    && inRange(x.floors, f.floors)
    && inRange(x.ppsqm_usd, f.ppsqm)
    && inRange(depositOf(x), f.deposit)
    && (!f.notfirst || (x.floor ?? 0) > 1)
    && (!f.notlast || (x.floor != null && x.floors != null && x.floor < x.floors))
    && (!f.tenants || (x.tenants ?? 0) >= +f.tenants)
    && (!f.seats || x.seats === +f.seats)
    && (!f.pickup || x.pickup === f.pickup));
}

type Cmp = (a: Row, b: Row) => number;
const SORTS: Record<string, Cmp> = {
  new: (a, b) => (b.ts ?? 0) - (a.ts ?? 0),
  cheap: (a, b) => (a.price_usd ?? Infinity) - (b.price_usd ?? Infinity),
  expensive: (a, b) => (b.price_usd ?? -1) - (a.price_usd ?? -1),
  area: (a, b) => (b.area ?? -1) - (a.area ?? -1),
  year: (a, b) => (b.year ?? -1) - (a.year ?? -1),
  ppsqm: (a, b) => (a.ppsqm_usd ?? Infinity) - (b.ppsqm_usd ?? Infinity),
};
export const sortItems = <T extends Row>(rows: T[], sort: string): T[] => rows.sort(SORTS[sort] || SORTS.new);

export function countBy(items: Partial<Item>[], key: keyof Item): [string, number][] {
  const map = new Map<string, number>();
  items.forEach(x => { const v = x[key]; if (v != null && v !== '') map.set(String(v), (map.get(String(v)) || 0) + 1); });
  return [...map.entries()].sort((a, b) => b[1] - a[1]);
}

/** How many of the listings were published in the last `days` days. */
export const publishedWithin = (items: Pick<Item, 'ts'>[], days: number) => items.filter(x => Date.now() - x.ts < days * 864e5).length;

/** "all" is the cross-service real-estate search, so cars stay out of it. */
export const itemsFor = <T extends Pick<Item, 'kind' | 'service'>>(items: T[], service: string): T[] =>
  items.filter(x => (service === 'all' ? x.kind !== 'car' : x.service === service));
