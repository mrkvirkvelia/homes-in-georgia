import type { MetadataRoute } from 'next';
import { fetchFeed } from '@/lib/api';
import { SERVICE_IDS } from '@/lib/config';

export const dynamic = 'force-dynamic';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = 'https://hge.ge';
  const feed = await fetchFeed().catch(() => null);
  const live = SERVICE_IDS.filter(s => (feed?.counts?.[s] || 0) > 0);
  return [
    { url: base, changeFrequency: 'hourly', priority: 1 },
    { url: `${base}/all`, changeFrequency: 'hourly', priority: 0.8 },
    ...live.map(s => ({ url: `${base}/${s}`, changeFrequency: 'hourly' as const, priority: 0.8 })),
    { url: `${base}/map`, changeFrequency: 'daily', priority: 0.5 },
    ...(feed?.items || []).map(x => ({ url: `${base}/listing/${x.id}`, lastModified: x.updated_at || x.published_at, changeFrequency: 'daily' as const, priority: 0.6 })),
  ];
}
