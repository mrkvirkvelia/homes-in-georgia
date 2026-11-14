// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// "Recently viewed": the ids are in the visitor's browser, so the row is drawn there (the feed is fetched only when there are any).
import Rail from './Rail';
import { useFmt } from './Providers';
import { useFeed } from '@/lib/feed-client';
import { useRecentIds } from '@/lib/favorites';

export default function RecentRail() {
  const { t } = useFmt();
  const ids = useRecentIds();
  const feed = useFeed(ids.length > 0);
  if (!feed) return null;
  const items = ids.map(id => feed.items.find(x => x.id === id || x.legacy_id === id)).filter(x => !!x);
  return <Rail id="rail-recent" title={t('home.recent')} items={items} />;
}
