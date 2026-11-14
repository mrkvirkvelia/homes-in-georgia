// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Browser only: runs a page's ported module on the container the server already filled.
import { initLang } from '@/legacy/i18n.js';
import { markLive } from '@/legacy/config.js';
import { loadFeed, setRates, prepareItem, parseFilters, filtersToParams } from '@/legacy/store.js';
import { loadingView, errorView } from '@/legacy/components.js';
import { renderHome } from '@/legacy/pages/home.js';
import { renderCatalog } from '@/legacy/pages/catalog.js';
import { renderListing } from '@/legacy/pages/listing.js';
import { renderMap } from '@/legacy/pages/map.js';
import { renderSoon, renderFavorites, notFoundMarkup } from '@/legacy/pages/misc.js';
import { openFilterSheet } from '@/legacy/filters.js';
import { replaceUrl } from '@/legacy/nav.js';
import type { Item, Feed } from './api';

if (typeof window !== 'undefined') initLang(); // the saved language / browser language, before anything renders

export type PageKind = 'home' | 'catalog' | 'listing' | 'map' | 'soon' | 'favorites' | 'notfound';
export interface Mounted { update?: (p: URLSearchParams) => void; destroy?: () => void }
interface Opts { arg: string; detail: Item | null; params: URLSearchParams; onQuery: (q: string) => void }

export const getFeed = async (): Promise<Feed> => {
  const data = await loadFeed();
  setRates(data.rates_usd);
  markLive(data.counts);
  return data;
};

export async function mountPage(kind: PageKind, root: HTMLElement, o: Opts): Promise<Mounted | null> {
  let data: Feed;
  try {
    data = await getFeed();
  } catch {
    root.innerHTML = errorView();
    root.querySelector('[data-retry]')?.addEventListener('click', () => { root.innerHTML = loadingView(); mountPage(kind, root, o); });
    return null;
  }
  document.body.classList.remove('map-page');
  switch (kind) {
    case 'home': renderHome(root, data); return null;
    case 'catalog': return renderCatalog(root, data, o.arg, o.params) ?? null;
    case 'soon': renderSoon(root, o.arg); return null;
    case 'favorites': renderFavorites(root, data); return null;
    case 'notfound': root.innerHTML = notFoundMarkup(); return null;
    case 'listing': {
      // The feed item plus the detail record (full description, video) that the server fetched.
      const base = data.byId.get(o.arg);
      const x = o.detail ? prepareItem({ ...base, ...o.detail }) : base;
      renderListing(root, data, x);
      return null;
    }
    case 'map': return mountMap(root, data, o);
  }
}

// /map keeps its state in the address: filters (q, price, district…), ch/age switches, from=<service>.
function mountMap(root: HTMLElement, data: Feed, o: Opts): Mounted {
  let params = o.params;
  let page: { destroy?: () => void } | null = null;
  const write = (q: URLSearchParams) => {
    params = q;
    o.onQuery(q.toString());
    replaceUrl(location.pathname + (q.toString() ? '?' + q : ''));
  };
  const draw = () => {
    page?.destroy?.();
    page = renderMap(root, data, params, {
      onState: write,
      onFilters: () => openFilterSheet({
        serviceId: 'all', base: data.items, filters: parseFilters(params),
        onApply: (next: unknown) => { write(filtersToParams(next, params)); draw(); },
      }),
      onReset: () => {
        const keep = new URLSearchParams();
        ['ch', 'age'].forEach(k => { const v = params.get(k); if (v) keep.set(k, v); });
        write(keep);
        draw();
      },
    });
  };
  draw();
  return { update: p => { params = p; draw(); }, destroy: () => page?.destroy?.() };
}
