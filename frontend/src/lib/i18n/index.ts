// CRM UI languages (David 11-15: «три языка для срм»). The Russian text is the key: ru shows it as is, ka/en look it up
// and fall back to Russian when a string has no translation yet. The choice lives in localStorage; switching reloads
// the page, so module-level labels (NAV, ROLE_LABEL…) are built in the right language. Generated documents and
// Telegram posts are not touched by this.
import { D as shell } from './shell';
import { D as core } from './core';
import { D as properties } from './properties';
import { D as detail } from './detail';
import { D as leads } from './leads';
import { D as contracts } from './contracts';
import { D as admin } from './admin';

export type Lang = 'ru' | 'ka' | 'en';
export const LANGS: { value: Lang; label: string }[] = [{ value: 'ru', label: 'RU' }, { value: 'ka', label: 'KA' }, { value: 'en', label: 'EN' }];
const KEY = 'hig_lang';

function read(): Lang {
  try { const v = localStorage.getItem(KEY); return v === 'ka' || v === 'en' ? v : 'ru'; } catch { return 'ru'; }
}
export const LANG: Lang = read();
if (typeof document !== 'undefined') document.documentElement.lang = LANG;

const DICT: Record<string, [string, string]> = { ...shell, ...core, ...properties, ...detail, ...leads, ...contracts, ...admin };

let cur: Lang = LANG;
/** The owner's public sign page (/sign/<token>) has its own language switch: shared components it renders (the extract
 * link, the registry list) follow it without a reload. CRM pages never call this. */
export function setPageLang(l: Lang) { cur = l; }

/** t('Объекты') → «ობიექტები» / «Properties»; t('Найдено {n}', { n: 5 }) fills {n}. */
export function t(ru: string, params?: Record<string, string | number>): string {
  let s = cur === 'ru' ? ru : DICT[ru]?.[cur === 'ka' ? 0 : 1] || ru;
  if (params) for (const [k, v] of Object.entries(params)) s = s.split(`{${k}}`).join(String(v));
  return s;
}
/** For text a dictionary key can't hold (plurals, built strings): lx(ru, ka, en). */
export function lx<T>(ru: T, ka: T, en: T): T { return LANG === 'ka' ? ka : LANG === 'en' ? en : ru; }
/** Translates the values of a label map once (ROLE_LABEL, PROPERTY_STATUS…). */
export function tmap<K extends string>(m: Record<K, string>): Record<K, string> {
  return Object.fromEntries(Object.entries(m).map(([k, v]) => [k, t(v as string)])) as Record<K, string>;
}
export const LOCALE = lx('ru-RU', 'ka-GE', 'en-GB');

export function setLang(l: Lang) {
  try { localStorage.setItem(KEY, l); } catch { /* private mode: stays ru */ }
  location.reload();
}
