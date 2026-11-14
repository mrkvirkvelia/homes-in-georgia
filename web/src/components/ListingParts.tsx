// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Interactive pieces of the listing page: back button, share / save actions, gallery with lightbox, expandable
// description and amenities, the location map, the "viewed" note.
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Icon } from './Icon';
import FavButton from './FavButton';
import { useSite } from './Providers';
import { addRecent } from '@/lib/favorites';
import { useLockBody } from '@/lib/hooks';
import { cameFromSite, scrollRoot } from '@/lib/scroll';
import { brandMap, loadLeaflet, mapTiler } from '@/lib/leaflet';
import { pricePin } from '@/lib/map-pins';
import type { Item } from '@/lib/types';

export function BackButton({ service }: { service: string }) {
  const { t } = useSite().fmt;
  const router = useRouter();
  return <button type="button" className="l-back" onClick={() => { if (cameFromSite()) history.back(); else router.push('/' + service); }}><Icon name="left" /><span>{t('nav.back')}</span></button>;
}

/** Counts the listing as recently viewed (the "Recently viewed" row of the home page). */
export function RecordView({ item }: { item: Item }) {
  useEffect(() => { addRecent(item); }, [item]);
  return null;
}

export function ShareFav({ item }: { item: Item }) {
  const { fmt, share } = useSite();
  return <>
    <button type="button" className="btn btn-outline" onClick={() => share(item)}><Icon name="share" /><span>{fmt.t('l.share')}</span></button>
    <FavButton item={item} className="btn btn-outline fav-inline" label />
  </>;
}

function Lightbox({ photos, start, title, onClose }: { photos: string[]; start: number; title: string; onClose: () => void }) {
  const { t } = useSite().fmt;
  const track = useRef<HTMLDivElement>(null);
  const [i, setI] = useState(start);
  useLockBody();
  const go = (n: number, smooth = true) => {
    const el = track.current;
    if (el) el.scrollTo({ left: Math.max(0, Math.min(photos.length - 1, n)) * el.clientWidth, behavior: smooth ? 'smooth' : 'auto' });
  };
  const goRef = useRef(go);
  const iRef = useRef(i);
  useEffect(() => { goRef.current = go; iRef.current = i; });
  useEffect(() => {
    requestAnimationFrame(() => goRef.current(start, false));
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') goRef.current(iRef.current + 1);
      if (e.key === 'ArrowLeft') goRef.current(iRef.current - 1);
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [start, onClose]);
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={title}>
      <div className="lb-top"><span className="lb-count">{i + 1} / {photos.length}</span><button className="icon-btn" autoFocus onClick={onClose} aria-label={t('nav.close')}><Icon name="x" /></button></div>
      <div className="lb-track" ref={track} onScroll={e => setI(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}>
        {photos.map(p => <figure key={p}>{}<img src={p} alt={title} loading="lazy" decoding="async" /></figure>)}
      </div>
      <button className="lb-nav prev" onClick={() => go(i - 1)} aria-label={t('card.prev')}><Icon name="left" /></button>
      <button className="lb-nav next" onClick={() => go(i + 1)} aria-label={t('card.next')}><Icon name="right" /></button>
    </div>
  );
}

/** Desktop mosaic of up to five photos, phone carousel, and the full-screen viewer (full-size photos). */
export function Gallery({ photos, title }: { photos: string[]; title: string }) {
  const { t } = useSite().fmt;
  const [open, setOpen] = useState<number | null>(null);
  const [current, setCurrent] = useState(0);
  if (!photos.length) return null;
  return <>
    <div className={`gallery g${Math.min(photos.length, 5)}`}>
      {photos.slice(0, 5).map((src, i) => (
        <button key={src} type="button" className="g-item" onClick={() => setOpen(i)} aria-label={`${title} · ${i + 1}`}>
          {}
          <img src={src} alt="" loading={i ? 'lazy' : undefined} fetchPriority={i ? undefined : 'high'} decoding="async" />
        </button>
      ))}
      {photos.length > 1 && <button type="button" className="btn btn-light g-all" onClick={() => setOpen(0)}><Icon name="image" /><span>{t('l.photos', photos.length)}</span></button>}
    </div>
    <div className="m-gallery">
      <div className="slides" data-slides onScroll={e => setCurrent(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}>
        {}
        {photos.map((src, i) => <img key={src} src={src} alt="" loading={i ? 'lazy' : undefined} onClick={() => setOpen(i)} />)}
      </div>
      <div className="dots" aria-hidden="true">{photos.slice(0, 12).map((src, i) => <i key={src} className={i === current ? 'on' : undefined} />)}</div>
    </div>
    {open !== null && <Lightbox photos={photos} start={open} title={title} onClose={() => setOpen(null)} />}
  </>;
}

/** The description, cut to a few lines, with "Show more" only when it really is cut. */
export function Description({ text }: { text: string }) {
  const { t } = useSite().fmt;
  const box = useRef<HTMLParagraphElement>(null);
  const [cut, setCut] = useState<boolean | null>(null); // null: not measured yet
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => setCut(c => (c === false || open ? c : el.scrollHeight > el.clientHeight + 4));
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);
  return <>
    <p ref={box} className={`l-desc${cut === false ? '' : ' clamp'}${open ? ' open' : ''}`}>
      {text.split('\n').map((line, i) => <span key={i}>{i > 0 && <br />}{line}</span>)}
    </p>
    <button type="button" className={`more-btn${open ? ' up' : ''}`} hidden={!cut} onClick={() => setOpen(!open)}>{t(open ? 'l.less' : 'l.more')} <Icon name="down" /></button>
  </>;
}

export function Amenities({ items }: { items: string[] }) {
  const { t } = useSite().fmt;
  const [open, setOpen] = useState(false);
  const long = items.length > 8;
  return <>
    <ul className={`amenities${long ? ' clamp' : ''}${open ? ' open' : ''}`}>{items.map(a => <li key={a}><Icon name="check" />{t('am.' + a)}</li>)}</ul>
    {long && <button type="button" className={`more-btn${open ? ' up' : ''}`} onClick={() => setOpen(!open)}>{open ? t('l.less') : t('l.amen.more', items.length)} <Icon name="down" /></button>}
  </>;
}

/** The location map: loaded only when it is about to be seen. */
export function LocationMap({ item: x }: { item: Item }) {
  const { fmt } = useSite();
  const el = useRef<HTMLDivElement>(null);
  const label = x.price_usd ? fmt.compactMoney(x.price_usd) : '•';
  useEffect(() => {
    const box = el.current;
    if (!box) return;
    let alive = true;
    let map: { remove: () => void } | undefined;
    const io = new IntersectionObserver(async ([entry]) => {
      if (!entry.isIntersecting) return;
      io.disconnect();
      const L = await loadLeaflet().catch(() => null);
      if (!L || !alive) return;
      const m = L.map(box, { zoomControl: false, scrollWheelZoom: false, dragging: !L.Browser.mobile, attributionControl: true }).setView([x.lat!, x.lon!], 15);
      map = m;
      L.control.zoom({ position: 'bottomright' }).addTo(m);
      brandMap(m);
      mapTiler(L, 'streets-v2').addTo(m);
      pricePin(L, x, label).addTo(m);
    }, { root: scrollRoot(), rootMargin: '300px' });
    io.observe(box);
    return () => { alive = false; io.disconnect(); map?.remove(); };
  }, [x, label]);
  return <div className="l-map" id="l-map" ref={el} />;
}
