// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Everything that depends on the visitor's language and currency: translations, prices, dates, place names.
// A plain object, so server components and client components (through context) use the same code.
import { translate, localeOf, type T } from './i18n';
import { placeName } from './places';
import type { Cur, Item, Lang } from './types';

const SYMBOL: Record<string, string> = { USD: '$', GEL: '₾', EUR: '€' };
const DEFAULT_RATES: Record<string, number> = { USD: 1, GEL: 1 / 2.7, EUR: 1.08 };

export interface PriceLabel { main: string; period: string; listed: string }
export interface Fmt {
  lang: Lang;
  cur: Cur;
  rates: Record<string, number>;
  t: T;
  num: (n: number) => string;
  money: (usd: number) => string;
  compactMoney: (usd: number) => string;
  fromUsd: (usd: number) => number;
  toUsd: (value: number) => number;
  symbol: string;
  priceLabel: (x: Item) => PriceLabel;
  sqmPrice: (x: Item) => string;
  depositUsd: (x: Item) => number | null;
  ago: (iso?: string) => string;
  place: (name?: string | null) => string;
  facts: (x: Item) => string[];
  title: (x: Item) => string;
}

export const listingTitle = (x: Item) => x.headline || x.title;
/** Short number shown on cards: "o547672" or the old "rent-547672" → "547672". */
export const shortId = (id?: string | null) => String(id || '').replace(/^\D+-/, '').replace(/^o(?=\d)/, '');
export const isFresh = (x: Item) => Date.now() - x.ts < 3 * 864e5;
// Price per square metre: the post's own figure, or price / area for flats, houses and offices.
const SQM_SERVICES = new Set(['rent', 'sale', 'commercial', 'new']);

export function createFmt(lang: Lang, cur: Cur, ratesUsd?: Record<string, number>): Fmt {
  const rates = { ...DEFAULT_RATES, ...(ratesUsd || {}) };
  const locale = localeOf(lang);
  const t: T = (key, ...args) => translate(lang, key, ...args);
  const num = (n: number) => Math.round(n).toLocaleString(locale).replace(/ /g, ' ');
  const money = (usd: number) => {
    const value = usd / rates[cur];
    return SYMBOL[cur] + num(value >= 10000 ? Math.round(value / 100) * 100 : value);
  };
  const compactMoney = (usd: number) => {
    const v = usd / rates[cur];
    const s = SYMBOL[cur];
    if (v >= 1e6) return s + (v / 1e6).toFixed(v >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (v >= 1e4) return s + Math.round(v / 1e3) + 'K';
    if (v >= 1e3) return s + (v / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
    return s + Math.round(v);
  };
  /** The price in the visitor's currency, plus the owner's own amount when it is in another currency. */
  const priceLabel = (x: Item): PriceLabel => {
    if (!x.price_usd) return { main: t('price.request'), period: '', listed: '' };
    const period = x.period ? t('period.' + x.period) : '';
    const own = x.price && x.currency && SYMBOL[x.currency] ? SYMBOL[x.currency] + num(x.price) : '';
    return x.currency === cur && own ? { main: own, period, listed: '' } : { main: money(x.price_usd), period, listed: own };
  };
  const sqmPrice = (x: Item) => {
    const usd = x.ppsqm_usd || (SQM_SERVICES.has(x.service) && x.price_usd && x.area ? x.price_usd / x.area : 0);
    if (!usd) return '';
    const value = usd / rates[cur];
    const text = value < 100 ? value.toLocaleString(locale, { maximumFractionDigits: 1 }) : num(value);
    return `${SYMBOL[cur]}${text} / m²`;
  };
  const ago = (iso?: string) => {
    const ts = Date.parse(iso || '');
    if (!ts) return '';
    const h = Math.floor((Date.now() - ts) / 36e5);
    if (h < 1) return t('ago.now');
    if (h < 24) return t('ago.h', h);
    const d = Math.floor(h / 24);
    if (d < 30) return t('ago.d', d);
    return new Date(ts).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const facts = (x: Item): string[] => {
    if (x.kind === 'car') {
      return [x.year, x.body ? t('body.' + x.body) : '', x.mileage ? `${num(x.mileage)} km` : '', x.gearbox ? t('gearbox.' + x.gearbox) : '', x.fuel ? t('fuel.' + x.fuel) : ''].filter(Boolean).map(String);
    }
    return [
      x.rooms != null ? t('card.beds', x.rooms) : x.kind !== 'apartment' ? t('kind.' + x.kind) : '',
      x.area ? `${Math.round(x.area)} m²` : '',
      x.floor ? t('card.floor', x.floor, x.floors) : '',
    ].filter(Boolean);
  };
  return {
    lang, cur, rates, t, num, money, compactMoney, symbol: SYMBOL[cur], priceLabel, sqmPrice, ago, facts,
    fromUsd: usd => usd / rates[cur],
    toUsd: value => value * rates[cur],
    depositUsd: x => (x.deposit && x.price && x.price_usd ? x.deposit * x.price_usd / x.price : null),
    place: name => placeName(name, lang),
    title: listingTitle,
  };
}

export const currencySymbol = (cur: string) => SYMBOL[cur] || '$';
