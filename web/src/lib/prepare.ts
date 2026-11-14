// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Clean-up of raw API items; runs on the server (lib/api.ts) and in the browser (lib/feed-client.ts).
import { canonicalPlace } from './places';
import type { Item } from './types';

// Safety net for listings built before the cleaner rules of the import.
const METRO_STATIONS = new Set(['Rustaveli', 'Liberty Square', 'Technical University', 'Medical University', 'State University', 'Delisi',
  'Vazha-Pshavela', 'Sarajishvili', 'Marjanishvili', '300 Aragveli', 'Station Square', 'Akhmeteli Theatre', 'Tsereteli', 'Grmagele', 'Guramishvili']);
const CAR_FIXES: [RegExp, string][] = [[/\bMersedes(?:[- ]Benz)?\b/gi, 'Mercedes-Benz'], [/\bMercedes(?![- ]Benz)\b/gi, 'Mercedes-Benz'], [/\bCompas\b/gi, 'Compass']];

/** Normalises one raw API item: drops nulls, canonical place names, clean car titles, timestamp. */
export function prepareItem(raw: Record<string, unknown>): Item {
  const x = Object.fromEntries(Object.entries(raw).filter(([, v]) => v !== null)) as unknown as Item;
  if (x.district) x.district = canonicalPlace(x.district);
  if (x.metro) x.metro = canonicalPlace(x.metro);
  if (x.district && !x.metro && METRO_STATIONS.has(x.district)) { x.metro = x.district; delete x.district; }
  if (x.kind === 'car' && x.title) {
    x.title = x.title.split(/\s*\|\s*|\s+(?:19|20)\d\d\s*[$₾€]/)[0].trim();
    CAR_FIXES.forEach(([re, good]) => { x.title = x.title.replace(re, good); });
  }
  x.ts = Date.parse(x.published_at || '') || 0;
  return x;
}
