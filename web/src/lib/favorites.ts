// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Favourites and recently viewed listings live in the visitor's browser (localStorage), as before.
// Old ids ("rent-551776") saved by the previous site stay valid: an item matches by its id or its legacy_id.
import { useSyncExternalStore } from 'react';
import type { Item } from './types';

const read = (key: string): string[] => { try { const v = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; } };
const write = (key: string, value: string[]) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* not remembered */ } };

function createStore(key: string) {
  const EMPTY: string[] = [];
  let ids: string[] = EMPTY;
  let loaded = false;
  const listeners = new Set<() => void>();
  const load = () => { if (!loaded && typeof window !== 'undefined') { loaded = true; ids = read(key); } };
  const emit = () => listeners.forEach(fn => fn());
  const onStorage = (e: StorageEvent) => { if (e.key === key) { ids = read(key); emit(); } };
  return {
    use: () => useSyncExternalStore(
      cb => { load(); listeners.add(cb); if (listeners.size === 1) addEventListener('storage', onStorage); return () => { listeners.delete(cb); if (!listeners.size) removeEventListener('storage', onStorage); }; },
      () => { load(); return ids; },
      () => EMPTY,
    ),
    get: () => { load(); return ids; },
    set(next: string[]) { load(); ids = next; write(key, next); emit(); },
  };
}

const favs = createStore('hig:fav');
const recents = createStore('hig:recent');

export const useFavIds = favs.use;
export const useRecentIds = recents.use;
const has = (ids: string[], x: Pick<Item, 'id' | 'legacy_id'>) => ids.includes(x.id) || (!!x.legacy_id && ids.includes(x.legacy_id));
export const useIsFav = (x: Pick<Item, 'id' | 'legacy_id'>) => has(favs.use(), x);

export function toggleFav(x: Pick<Item, 'id' | 'legacy_id'>): boolean {
  const ids = favs.get();
  const on = !has(ids, x);
  favs.set(on ? [...ids, x.id] : ids.filter(id => id !== x.id && id !== x.legacy_id));
  return on;
}

export function addRecent(x: Pick<Item, 'id' | 'legacy_id'>) {
  const next = [x.id, ...recents.get().filter(id => id !== x.id && id !== x.legacy_id)].slice(0, 12);
  recents.set(next);
}
