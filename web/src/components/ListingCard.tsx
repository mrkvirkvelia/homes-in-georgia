// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
import { Fragment, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Icon } from './Icon';
import FavButton from './FavButton';
import { useSite } from './Providers';
import { thumb } from '@/lib/photos';
import { isFresh, shortId } from '@/lib/format';
import type { Item } from '@/lib/types';

interface Props { item: Item; eager?: boolean; onHover?: (id: string | null) => void }

/** A listing card: photo carousel (a card loads only its first photo; the others load as the visitor reaches them),
 *  badges, share and save buttons, price and facts. Tapping a photo opens the listing. */
export default function ListingCard({ item: x, eager = false, onHover }: Props) {
  const { fmt, share } = useSite();
  const { t } = fmt;
  const router = useRouter();
  const track = useRef<HTMLDivElement>(null);
  const [reached, setReached] = useState(0); // photos up to this number are loaded
  const [current, setCurrent] = useState(0);
  const photos = (x.photos || []).slice(0, 9);
  const p = fmt.priceLabel(x);
  const sub = fmt.sqmPrice(x);
  const title = fmt.title(x);

  const index = () => { const el = track.current; return el && el.clientWidth ? Math.round(el.scrollLeft / el.clientWidth) : 0; };
  const wake = (upto: number) => setReached(r => Math.max(r, Math.min(upto, photos.length - 1)));
  const prime = () => wake(index() + 1); // touching a card's photos gets the next one ready before the swipe lands
  const slide = (dir: number) => {
    wake(index() + 2);
    track.current?.scrollBy({ left: track.current.clientWidth * dir, behavior: 'smooth' });
  };
  const onScroll = () => { const i = index(); setCurrent(i); wake(i + 1); };

  return (
    <article className="card" data-id={x.id} data-listing={x.id} data-service={x.service} data-agent={x.agent?.telegram || x.agent?.name || ''}
      onPointerEnter={onHover && (() => onHover(x.id))} onPointerLeave={onHover && (() => onHover(null))}>
      <div className="card-media">
        <div className="slides" data-slides ref={track} onScroll={onScroll} onPointerDown={prime} onTouchStart={prime} onMouseOver={prime}
          onClick={() => router.push('/listing/' + x.id)}>
          {photos.length ? photos.map((src, i) => (
            <img key={src} src={i <= reached ? thumb(src) : undefined} alt={`${title}${i ? ' · ' + (i + 1) : ''}`}
              loading={i || !eager ? 'lazy' : undefined} fetchPriority={!i && eager ? 'high' : undefined} decoding="async" draggable={false} />
          )) : <div className="noimg"><Icon name="image" /></div>}
        </div>
        {photos.length > 1 && <>
          <button className="slide-btn prev" type="button" onClick={() => slide(-1)} aria-label={t('card.prev')}><Icon name="left" /></button>
          <button className="slide-btn next" type="button" onClick={() => slide(1)} aria-label={t('card.next')}><Icon name="right" /></button>
          <div className="dots" aria-hidden="true">{photos.map((src, i) => <i key={src} className={i === current ? 'on' : undefined} />)}</div>
        </>}
        <div className="badges">
          {x.exclusive && <span className="badge badge-accent">{t('card.exclusive')}</span>}
          {isFresh(x) && <span className="badge">{t('card.new')}</span>}
          {x.completion && <span className="badge">{t('card.completion', x.completion)}</span>}
          {x.service === 'commercial' && x.deal && <span className="badge">{t('deal.' + x.deal)}</span>}
        </div>
        <button className="card-share" type="button" onClick={() => share(x)} aria-label={t('l.share')}><Icon name="share" /></button>
        <FavButton item={x} />
      </div>
      <Link className="card-body" href={`/listing/${x.id}`} prefetch={false}>
        <div className="card-price"><b>{p.main}</b>{p.period && <span>{p.period}</span>}<small className="card-id" title={t('l.id')}>ID {shortId(x.id)}</small></div>
        {sub && <p className="card-sqm">{sub}</p>}
        <h3>{title}</h3>
        <p className="card-facts">{fmt.facts(x).map((f, i) => <Fragment key={i}>{i > 0 && <i />}{f}</Fragment>)}</p>
        <p className="card-loc"><Icon name="pin" /><span>{x.pickup || [fmt.place(x.district), x.metro && x.metro !== x.district ? fmt.place(x.metro) : ''].filter(Boolean).join(' · ') || t('city')}</span><time>{fmt.ago(x.published_at)}</time></p>
      </Link>
    </article>
  );
}
