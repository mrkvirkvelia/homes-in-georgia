// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import { dict } from './i18n-dict';
import type { Lang } from './types';

export const LANGS: Lang[] = ['en', 'ka', 'ru'];
export const isLang = (v: unknown): v is Lang => LANGS.includes(v as Lang);
export const localeOf = (l: Lang) => ({ en: 'en-GB', ka: 'ka-GE', ru: 'ru-RU' })[l];

/** Accept-Language header → one of our languages. */
export const langFromHeader = (h: string | null | undefined): Lang => {
  const l = String(h || '').toLowerCase().slice(0, 2);
  return isLang(l) ? l : 'en';
};

export type T = (key: string, ...args: unknown[]) => string;
export const translate = (lang: Lang, key: string, ...args: unknown[]): string => {
  const value = dict[lang][key] ?? dict.en[key];
  if (typeof value === 'function') return value(...args);
  return Array.isArray(value) ? value.join(', ') : (value ?? key);
};
/** A list message (e.g. the preview chips of a "coming soon" page). */
export const translateList = (lang: Lang, key: string): string[] => {
  const value = dict[lang][key] ?? dict.en[key];
  return Array.isArray(value) ? value : [];
};
