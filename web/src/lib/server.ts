// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Per-request setup of the shared render modules (language, currency, which services are live).
// The render functions are synchronous and keep these in module variables, so always call
// applyRequest() right before building markup, with no `await` in between.
import { cookies, headers } from 'next/headers';
import { setLang, langFromHeader } from '@/legacy/i18n.js';
import { setCurrency } from '@/legacy/store.js';
import { markLive } from '@/legacy/config.js';
import { fetchFeed, type Feed } from './api';

export interface Req { lang: string; cur: string; data: Feed | null }

export async function loadRequest(): Promise<Req> {
  const [ck, hd, data] = await Promise.all([cookies(), headers(), fetchFeed().catch(() => null)]);
  const lang = ck.get('hig_lang')?.value ?? langFromHeader(hd.get('accept-language'));
  const cur = ck.get('hig_cur')?.value === 'GEL' ? 'GEL' : 'USD';
  return { lang, cur, data };
}

export function applyRequest(r: Req) {
  setLang(r.lang, { persist: false });
  setCurrency(r.cur, { persist: false });
  if (r.data) markLive(r.data.counts);
}
