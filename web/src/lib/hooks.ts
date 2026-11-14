// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
import { useEffect, useSyncExternalStore } from 'react';

/** Page scroll is locked while a sheet or the lightbox is open (class `locked` on <body>). */
export function useLockBody(on = true) {
  useEffect(() => {
    if (!on) return;
    document.body.classList.add('locked');
    return () => document.body.classList.remove('locked');
  }, [on]);
}

/** Media query that is false on the server and during hydration, then follows the screen. */
export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    cb => { const m = matchMedia(query); m.addEventListener('change', cb); return () => m.removeEventListener('change', cb); },
    () => matchMedia(query).matches,
    () => false,
  );
}
export const useDesktop = (px = 1100) => useMedia(`(min-width: ${px}px)`);

/** The theme is `data-theme="dark"` on <html> (set before the first paint, switched in the header). */
export function useDark(): boolean {
  return useSyncExternalStore(
    cb => { const o = new MutationObserver(cb); o.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }); return () => o.disconnect(); },
    () => document.documentElement.dataset.theme === 'dark',
    () => false,
  );
}
