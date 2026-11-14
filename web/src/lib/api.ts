// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Server side access to the CRM public API (contract: GET /api/public/site/listings, GET /api/public/site/listings/{id}).
import { cache } from 'react';
import { prepareItem } from './prepare';
import type { Feed, Item } from './types';

const API = () => process.env.API_URL || 'http://api:8000';

/** The whole feed (revalidated every 60 s by the data cache; deduplicated within one request). */
export const fetchFeed = cache(async (): Promise<Feed> => {
  const r = await fetch(`${API()}/api/public/site/listings`, { next: { revalidate: 60 } });
  if (!r.ok) throw new Error(`feed ${r.status}`);
  const data = await r.json() as Omit<Feed, 'items'> & { items: Record<string, unknown>[] };
  return { ...data, items: data.items.map(prepareItem) };
});

/** One listing with the full description and video; `id` is "o12", "s5", "c3" or an old id like "rent-551776". null = not public. */
export const fetchListing = cache(async (id: string): Promise<Item | null> => {
  const r = await fetch(`${API()}/api/public/site/listings/${encodeURIComponent(id)}`, { next: { revalidate: 60 } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`listing ${r.status}`);
  return prepareItem(await r.json());
});

export const findInFeed = (feed: Feed, id: string): Item | undefined => feed.items.find(x => x.id === id || x.legacy_id === id);
