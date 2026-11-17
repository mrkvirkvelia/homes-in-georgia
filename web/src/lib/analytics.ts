// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Our own site analytics: no Google, no cookies, no names or phone numbers.
// Short anonymous events go to the CRM (POST /api/public/site/events → table site_events) and are read only by
// superadmins in CRM «Аналитика». If the endpoint is down, the site does not notice.
import { ANALYTICS_URL, CHANNELS } from './config';

type Extra = Record<string, unknown>;
const MAX_ERRORS = 5;
const queue: Extra[] = [];
let timer: ReturnType<typeof setTimeout> | 0 = 0;
let searchTimer: ReturnType<typeof setTimeout> | 0 = 0;
let errors = 0;
let active = false;
let lastPath = '';
interface Source { src: string; med: string; cmp: string }
interface Ctx extends Source { visitor: string; session: string; isNew: boolean }
let ctx: Ctx | null = null;

const store = (area: 'localStorage' | 'sessionStorage', key: string, make: () => string): [string, boolean] => {
  try {
    let v = window[area].getItem(key);
    if (!v) { v = make(); window[area].setItem(key, v); return [v, true]; }
    return [v, false];
  } catch { return [make(), true]; }
};
const rid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);

// Where a visit came from: link tags first, then the page that sent the visitor.
const SOURCES: [RegExp, string][] = [
  [/instagram\./, 'instagram'], [/(^|\.)facebook\.|^fb\.|^l\.facebook|^m\.facebook/, 'facebook'],
  [/tiktok\./, 'tiktok'], [/youtube\.|youtu\.be/, 'youtube'], [/threads\.(net|com)/, 'threads'],
  [/^t\.me$|telegram\./, 'telegram'], [/whatsapp\.|wa\.me/, 'whatsapp'], [/viber\./, 'viber'],
  [/google\./, 'google'], [/yandex\./, 'yandex'], [/bing\./, 'bing'],
  [/myhome\.ge/, 'myhome'], [/ss\.ge/, 'ss.ge'],
];
const DIRECT: Source = { src: 'direct', med: '', cmp: '' };
export function sourceOf(href: string, referrer: string): Source {
  const own = new URL(href);
  const p = own.searchParams;
  const utm = p.get('utm_source');
  if (utm) return { src: utm.toLowerCase(), med: p.get('utm_medium') || '', cmp: p.get('utm_campaign') || '' };
  if (!referrer) return DIRECT;
  let ref: URL;
  try { ref = new URL(referrer); } catch { return DIRECT; }
  if (ref.host === own.host) return DIRECT;
  const host = ref.host.replace(/^www\./, '');
  const hit = SOURCES.find(([re]) => re.test(host));
  return { src: hit ? hit[1] : host, med: '', cmp: '' };
}

function context(): Ctx {
  if (ctx) return ctx;
  const [visitor, isNew] = store('localStorage', 'hig:vid', rid);
  const [session, fresh] = store('sessionStorage', 'hig:sid', rid);
  let origin: Source | null = null;
  if (fresh) {
    origin = sourceOf(location.href, document.referrer);
    try { sessionStorage.setItem('hig:src', JSON.stringify(origin)); } catch { /* fine */ }
  } else {
    try { origin = JSON.parse(sessionStorage.getItem('hig:src') || 'null'); } catch { origin = null; }
  }
  ctx = { visitor, session, isNew, ...(origin || DIRECT) };
  return ctx;
}

const pagePath = () => location.pathname + location.search;
const device = () => (matchMedia('(max-width: 759px)').matches ? 'mobile' : matchMedia('(max-width: 1023px)').matches ? 'tablet' : 'desktop');

function track(type: string, extra: Extra = {}) {
  if (!ANALYTICS_URL || !active) return;
  const c = context();
  queue.push({
    t: type, v: c.visitor, s: c.session, nw: c.isNew, src: c.src, med: c.med, cmp: c.cmp,
    p: pagePath(), lang: document.documentElement.lang || '',
    th: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light', dev: device(),
    ...extra,
  });
  c.isNew = false;
  if (queue.length >= 10) flush();
  else if (!timer) timer = setTimeout(flush, 4000);
}

function flush(leaving = false) {
  if (timer) clearTimeout(timer);
  timer = 0;
  if (!queue.length || !ANALYTICS_URL) return;
  const body = JSON.stringify({ events: queue.splice(0, 50) });
  try {
    // text/plain: no preflight, and sendBeacon sends the same body.
    if (leaving === true && navigator.sendBeacon && navigator.sendBeacon(ANALYTICS_URL, body)) return;
    fetch(ANALYTICS_URL, { method: 'POST', body, keepalive: true, headers: { 'Content-Type': 'text/plain' } }).catch(() => {});
  } catch { /* analytics must never break the site */ }
}

// Listing facts the report groups by (direction and agent) come from data attributes on the listing's own markup.
interface Info { l?: string; sv?: string; ag?: string }
const infoOf = (el: Element | null): Info => {
  const scope = el?.closest<HTMLElement>('[data-listing]');
  return scope ? { l: scope.dataset.listing, sv: scope.dataset.service || '', ag: scope.dataset.agent || '' } : {};
};
const info = (el: Element): Info => {
  const scope = infoOf(el);
  if (scope.l) return scope;
  const m = location.pathname.match(/^\/listing\/([^?/]+)/);
  return m ? { ...infoOf(document.querySelector('[data-listing]')), l: decodeURIComponent(m[1]) } : {};
};

/** Called on every navigation (and once on load): one page view, plus the listing the page is about. */
export function trackRoute() {
  const path = pagePath();
  if (!active || path === lastPath) return;
  lastPath = path;
  track('pageview');
  const m = path.match(/^\/listing\/([^?/]+)/);
  if (m) track('listing', { ...infoOf(document.querySelector('[data-listing]')), l: decodeURIComponent(m[1]) });
}

// What a click means: a way of reaching us, a share, a favourite.
const CHANNEL_NAMES = new Set(Object.values(CHANNELS).map(c => c.toLowerCase()));
function channelOf(a: HTMLElement) {
  const href = a.getAttribute('href') || '';
  if (a.dataset.lead) return a.dataset.lead;
  if (href.startsWith('tel:')) return 'phone';
  if (/wa\.me|whatsapp/.test(href)) return 'whatsapp';
  const tg = href.match(/^https:\/\/t\.me\/([^/?#]+)/);
  if (tg && tg[1] !== 'share') return CHANNEL_NAMES.has(tg[1].toLowerCase()) ? '' : 'telegram';
  if (/google\.com\/maps/.test(href)) return 'office';
  return '';
}

function onClick(e: MouseEvent) {
  const el = (e.target as Element | null)?.closest?.<HTMLElement>('a, button');
  if (!el) return;
  const share = el.closest<HTMLElement>('.share-target[data-target]');
  if (share) return track('share', { ...info(el), x: { ch: share.dataset.target } });
  if (el.matches('[data-copy]') && el.closest('.share-wrap')) return track('share', { ...info(el), x: { ch: 'copy' } });
  if (el.matches('[data-fav]')) {
    // The button flips after this runs in the same click, so read it a moment later.
    setTimeout(() => track('fav', { ...info(el), l: el.dataset.fav, x: { on: el.getAttribute('aria-pressed') === 'true' } }), 0);
    return;
  }
  if (el.tagName !== 'A') return;
  const ch = channelOf(el);
  if (ch) return track('contact', { ...info(el), x: { ch } });
  // Our social accounts, portals and Telegram channels: interest, not a direct request.
  const tg = (el.getAttribute('href') || '').match(/^https:\/\/t\.me\/([^/?#]+)/);
  if (tg && CHANNEL_NAMES.has(tg[1].toLowerCase())) return track('social', { x: { ch: 'telegram:' + tg[1] } });
  if (el.dataset.social) return track('social', { x: { ch: el.dataset.social } });
  if (el.matches('.foot-chip')) {
    const name = (el.querySelector('b')?.textContent || '').trim().toLowerCase();
    const handle = (el.querySelector('small')?.textContent || '').trim();
    track('social', { x: { ch: handle.startsWith('@') || /\./.test(handle) && name !== 'myhome.ge' && name !== 'ss.ge' ? `${name} ${handle}` : name } });
  }
}

/** The catalogue reports each finished search; the last one in a burst of typing is kept. */
export function trackSearch(service: string, params: string, count: number) {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (!params) return; // an unfiltered list is browsing, not a search
    track('search', { sv: service, x: { q: params, n: count } });
  }, 1500);
}

// Noise from in-app browsers (FB/IG), extensions and cross-origin scripts, not our code.
const NOISE = /Java object is gone|enableDidUserTypeOnKeyboardLogging|Error invoking postMessage|^Script error\.?(\s|$)|(chrome|moz|safari)-extension:|fbq?events|fburl|webkit\.messageHandlers|window\.ethereum/i;

function onError(message: unknown, where: unknown) {
  if (NOISE.test(`${message} ${where}`)) return;
  if (errors >= MAX_ERRORS) return;
  errors++;
  track('error', { x: { msg: String(message || 'error').slice(0, 200), at: String(where || '').split('/').pop()!.slice(0, 120) } });
}

function measure() {
  let lcp = 0;
  try {
    new PerformanceObserver(list => { const e = list.getEntries().pop(); if (e) lcp = Math.round(e.startTime); })
      .observe({ type: 'largest-contentful-paint', buffered: true });
  } catch { /* not every browser has it */ }
  addEventListener('load', () => setTimeout(() => {
    const nav = performance.getEntriesByType?.('navigation')?.[0] as PerformanceNavigationTiming | undefined;
    const load = nav ? Math.round(nav.loadEventEnd || nav.domComplete) : 0;
    if (load > 0) track('perf', { x: { load, lcp } });
  }, 3000), { once: true });
}

let started = false;
/** Once per page load. Our own automated tests and robots are not visitors. */
export function initAnalytics() {
  if (started) return;
  started = true;
  let testing = false;
  try { testing = localStorage.getItem('hig:analytics-test') === '1'; } catch { /* fine */ }
  if (!ANALYTICS_URL || (navigator.webdriver && !testing)) return;
  active = true;
  try {
    document.addEventListener('click', onClick, true);
    addEventListener('error', e => onError(e.message, `${e.filename || ''}:${e.lineno}`));
    addEventListener('unhandledrejection', e => onError(e.reason?.message || e.reason, 'promise'));
    addEventListener('pagehide', () => flush(true));
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(true); });
    measure();
  } catch { /* never break the site */ }
}
