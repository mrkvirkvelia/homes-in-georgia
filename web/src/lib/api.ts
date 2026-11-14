// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Server side access to the CRM public API (contract: /api/public/site/listings, /listings/{id}).
import { prepareFeed, prepareItem } from '@/legacy/store.js';

const API = () => process.env.API_URL || 'http://api:8000';

export interface Item {
  id: string;
  legacy_id: string | null;
  service: string;
  kind: string;
  title: string;
  headline?: string;
  description?: string;
  district?: string;
  price_usd?: number;
  period?: string;
  photos?: string[];
  video?: string | null;
  published_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}
export interface Feed {
  updated_at: string;
  rates_usd: Record<string, number>;
  counts: Record<string, number>;
  items: Item[];
  byId: Map<string, Item>;
  [key: string]: unknown;
}

export async function fetchFeed(): Promise<Feed> {
  const r = await fetch(`${API()}/api/public/site/listings`, { next: { revalidate: 60 } });
  if (!r.ok) throw new Error(`feed ${r.status}`);
  return prepareFeed(await r.json());
}

/** One listing with the full description and video; `id` is "o<pid>" or an old id like "rent-551776". null = not public. */
export async function fetchListing(id: string): Promise<Item | null> {
  const r = await fetch(`${API()}/api/public/site/listings/${encodeURIComponent(id)}`, { next: { revalidate: 60 } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`listing ${r.status}`);
  return prepareItem(await r.json());
}
