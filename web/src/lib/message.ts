// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// The message that opens a chat with the listing's agent. It carries the Telegram post link (in the chat it unfolds
// into the post with photos, so the agent sees the exact object at once) and the listing ID.
import { CONTACT, SITE_URL, telegramHref } from './config';
import type { Fmt } from './format';
import type { Item } from './types';

const SYMBOL: Record<string, string> = { USD: '$', GEL: '₾', EUR: '€' };

export function contactMessage(fmt: Fmt, x: Item) {
  const p = fmt.priceLabel(x);
  const objectLink = x.post_url || `${SITE_URL}/listing/${x.id}`;
  const symbol = SYMBOL[x.currency || ''] || '$';
  const listedPrice = x.price ? `${symbol}${fmt.num(x.price)}${p.period ? ' ' + p.period : ''}` : p.main;
  const message = fmt.t('l.msg', x.kind, fmt.title(x), listedPrice, objectLink) + `\nID: ${x.id}`;
  return { message, objectLink, tg: telegramHref(x.agent?.telegram || CONTACT.telegram, message), phone: x.agent?.phone || CONTACT.phone };
}
