// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// The whole feed in the browser, fetched from the same domain, only for the few places that need items the page
// did not receive from the server (saved listings, recently viewed, the "section" picker of the filter sheet).
import { useEffect, useState } from 'react';
import { prepareItem } from './prepare';
import type { Feed } from './types';

let feed: Promise<Feed> | undefined;
export function loadFeed(): Promise<Feed> {
  feed ??= fetch('/api/public/site/listings', { cache: 'no-cache' })
    .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((data: Omit<Feed, 'items'> & { items: Record<string, unknown>[] }) => ({ ...data, items: data.items.map(prepareItem) }))
    .catch(err => { feed = undefined; throw err; });
  return feed;
}

/** `undefined` while loading, `null` when it failed. Starts loading only when `enabled`. */
export function useFeed(enabled = true, attempt = 0): Feed | null | undefined {
  const [state, setState] = useState<{ attempt: number; feed: Feed | null } | undefined>();
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    loadFeed().then(f => alive && setState({ attempt, feed: f })).catch(() => alive && setState({ attempt, feed: null }));
    return () => { alive = false; };
  }, [enabled, attempt]);
  return state?.attempt === attempt ? state.feed : undefined;
}
