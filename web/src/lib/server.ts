// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Per-request setup for server components: the visitor's language and currency (cookies hig_lang / hig_cur, else
// Accept-Language), the feed, and the formatter built from them. Cached, so every component of a request shares it.
import { cache } from 'react';
import { cookies, headers } from 'next/headers';
import { fetchFeed } from './api';
import { createFmt, type Fmt } from './format';
import { isLang, langFromHeader } from './i18n';
import { SERVICE_IDS } from './config';
import type { Cur, Feed, Lang, ServiceId } from './types';

export interface Request { lang: Lang; cur: Cur; feed: Feed | null; fmt: Fmt; live: ServiceId[] }

export const getRequest = cache(async (): Promise<Request> => {
  const [ck, hd, feed] = await Promise.all([cookies(), headers(), fetchFeed().catch(() => null)]);
  const saved = ck.get('hig_lang')?.value;
  const lang: Lang = isLang(saved) ? saved : langFromHeader(hd.get('accept-language'));
  const cur: Cur = ck.get('hig_cur')?.value === 'GEL' ? 'GEL' : 'USD';
  return { lang, cur, feed, fmt: createFmt(lang, cur, feed?.rates_usd), live: SERVICE_IDS.filter(s => (feed?.counts?.[s] || 0) > 0) };
});
