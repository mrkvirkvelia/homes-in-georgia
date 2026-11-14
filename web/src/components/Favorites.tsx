// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
import { useState } from 'react';
import Link from 'next/link';
import ListingCard from './ListingCard';
import ErrorView from './ErrorView';
import { Empty, LoadingView } from './Empty';
import { useFmt } from './Providers';
import { useFeed } from '@/lib/feed-client';
import { useFavIds } from '@/lib/favorites';

/** Saved listings: the ids are in the visitor's browser; the listings come from the feed fetched there. */
export default function Favorites() {
  const { t } = useFmt();
  const ids = useFavIds();
  const [attempt, setAttempt] = useState(0);
  const feed = useFeed(true, attempt);
  if (feed === undefined) return <LoadingView text={t('loading')} />;
  if (feed === null) return <ErrorView onRetry={() => setAttempt(a => a + 1)} />;
  const items = ids.map(id => feed.items.find(x => x.id === id || x.legacy_id === id)).filter(x => !!x);
  return (
    <section className="container page-pad">
      <div className="cat-title"><h1>{t('fav.title')}</h1><span className="cat-count">{items.length ? t('cat.count', items.length) : ''}</span></div>
      {items.length
        ? <div className="grid grid-wide">{items.map(x => <ListingCard key={x.id} item={x} />)}</div>
        : <Empty title={t('fav.empty.t')} text={t('fav.empty.d')}><Link className="btn btn-primary" href="/rent">{t('fav.browse')}</Link></Empty>}
    </section>
  );
}
