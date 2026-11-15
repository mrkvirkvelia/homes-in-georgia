// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Shapes of the CRM public API (GET /api/public/site/listings and /listings/{id}).

export type Lang = 'en' | 'ka' | 'ru';
export type Cur = 'USD' | 'GEL';
export type ServiceId = 'rent' | 'sale' | 'commercial' | 'daily' | 'new' | 'car-rent' | 'car-sale';
export type Kind = 'apartment' | 'house' | 'commercial' | 'land' | 'car';

export interface Agent { telegram?: string; name?: string; phone?: string }

export interface Item {
  id: string; // "o<n>" rent, "s<n>" sales, "c<n>" cars
  legacy_id?: string | null; // old id like "rent-551776"
  service: ServiceId;
  source?: string;
  kind: Kind;
  deal?: 'rent' | 'sale';
  title: string;
  headline?: string;
  description?: string;
  district?: string;
  metro?: string;
  lat?: number;
  lon?: number;
  approx?: boolean;
  price?: number;
  currency?: string;
  price_usd?: number;
  period?: 'month' | 'night' | 'day' | 'hour';
  deposit?: number;
  ppsqm_usd?: number;
  rooms?: number;
  bathrooms?: number;
  type?: string; // the exact type when kind is a group: cafe, retail, duplex …
  area?: number;
  floor?: number;
  floors?: number;
  building?: string;
  condition?: string;
  heating?: string;
  amenities?: string[];
  year?: number;
  gearbox?: string;
  fuel?: string;
  body?: string;
  seats?: number;
  mileage?: number;
  pickup?: string;
  pets?: 'allowed' | 'agreement' | 'no';
  months?: number[];
  tenants?: number;
  exclusive?: boolean;
  completion?: string | number;
  agent?: Agent;
  photos?: string[];
  video?: string | null;
  post_url?: string;
  published_at?: string;
  updated_at?: string;
  ts: number; // published_at as a timestamp (added by lib/api.ts)
}

export interface Feed {
  updated_at: string;
  rates_usd: Record<string, number>;
  rates_source?: string;
  rates_date?: string;
  counts: Record<string, number>;
  items: Item[];
}
