// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Page scrolling and "come back to the same place": what the visitor was looking at (scroll position, map centre,
// open card) is remembered per address and restored on back/forward. Browser only.
const STORE = 'hig:positions';
const MAX_ENTRIES = 60;
const phone = typeof matchMedia === 'function' ? matchMedia('(max-width: 999px)') : { matches: false };
let currentKey: string | null = null, restoreToken = 0, popped = false, fromSite = false;

if (typeof window !== 'undefined') {
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  // The position is saved while the old page is still on screen: when a link is followed, or when back/forward starts.
  const remember = () => { if (currentKey) saveEntry({ top: pageTop() }); };
  addEventListener('popstate', () => { remember(); popped = true; });
  document.addEventListener('click', e => { if ((e.target as Element).closest?.('a[href]')) remember(); }, true);
}

// Phones scroll an inner area between the fixed header and tab bar; desktop scrolls the window.
export const scrollRoot = (): HTMLElement | null => (phone.matches ? document.getElementById('scroller') : null);
const scrollEl = () => scrollRoot() || document.scrollingElement || document.documentElement;
export const pageTop = () => scrollEl().scrollTop;
export const setPageTop = (y: number) => { scrollEl().scrollTop = y; };

export interface Entry { top?: number; center?: [number, number]; zoom?: number; card?: string | null }
const readAll = (): Record<string, Entry> => { try { return JSON.parse(sessionStorage.getItem(STORE) || '{}') || {}; } catch { return {}; } };
function writeAll(all: Record<string, Entry>) {
  const keys = Object.keys(all);
  keys.slice(0, Math.max(0, keys.length - MAX_ENTRIES)).forEach(k => delete all[k]);
  try { sessionStorage.setItem(STORE, JSON.stringify(all)); } catch { /* private mode: nothing to restore later */ }
}
const keyOf = () => location.pathname + location.search;

/** Extra state of the current entry, e.g. the map's centre and the open card. */
export const entryData = (): Entry => (currentKey && readAll()[currentKey]) || {};
export function saveEntry(patch: Entry) {
  if (!currentKey) return;
  const all = readAll();
  all[currentKey] = { ...all[currentKey], ...patch };
  writeAll(all);
}

/** Called on every navigation. True when the visitor came back/forward to a known entry. */
export function enterEntry(): boolean {
  const revisit = popped && !!readAll()[keyOf()];
  fromSite = fromSite || currentKey !== null;
  popped = false;
  currentKey = keyOf();
  return revisit;
}

/** True when this page was reached from another page of the site in this tab. */
export const cameFromSite = () => fromSite;

/** Lists grow as they scroll, so keep trying until the saved position exists. */
export function restoreTop() {
  const token = ++restoreToken;
  const target = entryData().top || 0;
  let tries = 0;
  const stop = () => { restoreToken++; };
  addEventListener('touchstart', stop, { once: true, passive: true });
  addEventListener('wheel', stop, { once: true, passive: true });
  const step = () => {
    if (token !== restoreToken) return;
    setPageTop(target);
    if (Math.abs(pageTop() - target) < 2 || ++tries > 60) return;
    setTimeout(step, 50);
  };
  step();
}
export const cancelRestore = () => { restoreToken++; };

/** The bottom bar must sit above the browser's own toolbar on every phone. */
export function watchViewport() {
  const fit = () => {
    const v = window.visualViewport;
    if (v && v.scale < 1.01) document.documentElement.style.setProperty('--app-h', v.height + 'px');
  };
  window.visualViewport?.addEventListener('resize', fit);
  addEventListener('orientationchange', fit);
  fit();
  return () => { window.visualViewport?.removeEventListener('resize', fit); removeEventListener('orientationchange', fit); };
}
