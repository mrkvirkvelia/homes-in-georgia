// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Glass share sheet: Telegram first, then WhatsApp, Facebook, Instagram, Viber, copy, system share.
import { useEffect, useRef, useState } from 'react';
import { Icon, BrandMark } from './Icon';
import { useFmt, useSite } from './Providers';
import { thumb } from '@/lib/photos';
import { SITE_URL } from '@/lib/config';
import { useLockBody } from '@/lib/hooks';
import type { Item } from '@/lib/types';

/** The listing page itself carries the preview (og:image, title, price) for messengers. `via` marks where the link was sent. */
export function shareUrl(x: Pick<Item, 'id'>, via = '') {
  const url = new URL(`/listing/${encodeURIComponent(x.id)}`, SITE_URL);
  url.search = via ? `utm_source=share&utm_medium=${encodeURIComponent(via)}` : '';
  return url.href;
}

async function copy(text: string) {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}

export default function ShareSheet({ item: x, onClose }: { item: Item; onClose: () => void }) {
  const fmt = useFmt();
  const { notify } = useSite();
  const { t } = fmt;
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const closing = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useLockBody();

  const p = fmt.priceLabel(x);
  const text = `${fmt.title(x)} — ${p.main}${p.period ? ' ' + p.period : ''}`;
  const url = shareUrl(x, 'link');
  const via = (ch: string) => shareUrl(x, ch);
  const canShare = typeof navigator !== 'undefined' && !!navigator.share;
  const targets: [string, string, string][] = [
    ['telegram', 'Telegram', `https://t.me/share/url?url=${encodeURIComponent(via('telegram'))}&text=${encodeURIComponent(text)}`],
    ['whatsapp', 'WhatsApp', `https://wa.me/?text=${encodeURIComponent(text + '\n' + via('whatsapp'))}`],
    ['facebook', 'Facebook', `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(via('facebook'))}`],
    ['instagram', 'Instagram', ''],
    ['viber', 'Viber', `viber://forward?text=${encodeURIComponent(text + '\n' + via('viber'))}`],
  ];

  const close = () => { setOpen(false); closing.current = setTimeout(onClose, 240); };
  const closeRef = useRef(close);
  useEffect(() => { closeRef.current = close; });
  useEffect(() => {
    const raf = requestAnimationFrame(() => setOpen(true));
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); };
    document.addEventListener('keydown', onKey);
    return () => { cancelAnimationFrame(raf); clearTimeout(closing.current); document.removeEventListener('keydown', onKey); };
  }, []);

  const doShare = async (ch: string) => {
    try { await navigator.share({ title: fmt.title(x), text, url: via(ch) }); return true; } catch { return false; }
  };
  const onTarget = async (key: string) => {
    if (key === 'native') { if (await doShare('native')) close(); }
    else if (key === 'instagram') {
      // Instagram has no web share link: hand the link to the system sheet (Instagram Direct / Stories), or copy it.
      if (canShare && await doShare('instagram')) { close(); return; }
      if (await copy(via('instagram'))) notify(t('share.insta'));
    } else setTimeout(close, 300);
  };
  const onCopy = async () => {
    if (await copy(url)) notify(t('l.copied'));
    input.current?.select();
  };

  return (
    <div className={`sheet-wrap share-wrap${open ? ' open' : ''}`} data-listing={x.id} data-service={x.service} data-agent={x.agent?.telegram || x.agent?.name || ''}>
      <div className="sheet-backdrop" onClick={close} />
      <aside className="sheet share-sheet" role="dialog" aria-modal="true" aria-labelledby="share-title">
        <header className="sheet-head"><span className="grab" /><h2 id="share-title">{t('share.title')}</h2>
          <button className="icon-btn" type="button" onClick={close} aria-label={t('nav.close')}><Icon name="x" /></button></header>
        <div className="share-body">
          <div className="share-preview">
            {x.photos?.[0] ? <img src={thumb(x.photos[0])} alt="" /> : <span className="noimg"><Icon name="image" /></span>}
            <div><b>{fmt.title(x)}</b><span>{text.split(' — ').slice(1).join(' — ')}</span></div>
          </div>
          <div className="share-grid">
            {targets.map(([key, label, href]) => {
              const inner = <><i className={`st-${key}`}><BrandMark name={key} /></i><span>{label}</span></>;
              return href
                ? <a key={key} className="share-target" href={href} target="_blank" rel="noopener" data-target={key} onClick={() => onTarget(key)}>{inner}</a>
                : <button key={key} type="button" className="share-target" data-target={key} onClick={() => onTarget(key)}>{inner}</button>;
            })}
            {canShare && <button type="button" className="share-target" data-target="native" onClick={() => onTarget('native')}><i className="st-more"><Icon name="share" /></i><span>{t('share.more')}</span></button>}
          </div>
          <div className="share-link">
            <input ref={input} type="text" readOnly value={url} aria-label={t('share.link')} />
            <button type="button" className="btn btn-primary" data-copy onClick={onCopy}><Icon name="check" /><span>{t('share.copy')}</span></button>
          </div>
        </div>
      </aside>
    </div>
  );
}
