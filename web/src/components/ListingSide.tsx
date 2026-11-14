// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Price card (contact buttons) beside the listing and the sticky bottom bar of phones.
import { Icon } from './Icon';
import FavButton from './FavButton';
import { useSite } from './Providers';
import { phoneHref, whatsappHref } from '@/lib/config';
import { contactMessage } from '@/lib/message';
import type { Item } from '@/lib/types';

/** Also copy the link, for Telegram versions that ignore the pre-filled text. */
function useCopyLink(link: string) {
  const { fmt, notify } = useSite();
  return () => { navigator.clipboard?.writeText(link).then(() => notify(fmt.t('l.msg.copied'))).catch(() => {}); };
}

export function PriceCard({ item: x }: { item: Item }) {
  const { fmt } = useSite();
  const { t } = fmt;
  const p = fmt.priceLabel(x);
  const sqm = fmt.sqmPrice(x);
  const dep = fmt.depositUsd(x);
  const { message, objectLink, tg, phone } = contactMessage(fmt, x);
  const copy = useCopyLink(objectLink);
  return (
    <div className="price-card">
      <div className="pc-price"><b>{p.main}</b>{p.period && <span>{p.period}</span>}</div>
      {sqm && <p className="pc-sqm">{sqm}</p>}
      {p.listed && <p className="pc-approx">{t('l.approx')}: {p.listed}{p.period ? ' ' + p.period : ''}</p>}
      <dl className="pc-rows">
        {x.deposit && <div><dt>{t('l.deposit')}</dt><dd>{dep ? fmt.money(dep) : ''}</dd></div>}
        {sqm && <div><dt>{t('l.ppsqm')}</dt><dd>{sqm}</dd></div>}
      </dl>
      <a className="btn btn-primary btn-lg btn-block" href={tg} target="_blank" rel="noopener" data-lead="telegram" onClick={copy}><Icon name="send" /><span>{t('l.write')}</span></a>
      <div className="pc-two">
        <a className="btn btn-outline" href={phoneHref(phone)} data-lead="phone"><Icon name="phone" /><span>{t('l.call')}</span></a>
        <a className="btn btn-outline" href={whatsappHref(phone, message)} target="_blank" rel="noopener" data-lead="whatsapp"><Icon name="whatsapp" /><span>{t('l.whatsapp')}</span></a>
      </div>
      {x.agent?.telegram && <p className="pc-agent">@{x.agent.telegram} · {phone}</p>}
    </div>
  );
}

export function StickyBar({ item: x }: { item: Item }) {
  const { fmt, share } = useSite();
  const { t } = fmt;
  const p = fmt.priceLabel(x);
  const { objectLink, tg } = contactMessage(fmt, x);
  const copy = useCopyLink(objectLink);
  return (
    <div className="l-sticky">
      <div className="ls-price"><b>{p.main}</b><span>{[p.period, fmt.sqmPrice(x)].filter(Boolean).join(' · ') || ' '}</span></div>
      <button type="button" className="icon-btn" onClick={() => share(x)} aria-label={t('l.share')}><Icon name="share" /></button>
      <FavButton item={x} className="fav fav-plain" />
      <a className="btn btn-primary" href={tg} target="_blank" rel="noopener" data-lead="telegram" onClick={copy}><Icon name="send" /><span>{t('l.write.short')}</span></a>
    </div>
  );
}
