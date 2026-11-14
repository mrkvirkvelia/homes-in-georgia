// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
import { useRef } from 'react';
import Link from 'next/link';
import { Icon } from './Icon';
import ListingCard from './ListingCard';
import { useFmt } from './Providers';
import type { Item } from '@/lib/types';

/** A horizontal row of cards with a title, an optional "see all" link and arrow buttons. */
export default function Rail({ id, title, items, href }: { id: string; title: string; items: Item[]; href?: string }) {
  const { t } = useFmt();
  const rail = useRef<HTMLDivElement>(null);
  if (!items.length) return null;
  const scroll = (dir: number) => rail.current?.scrollBy({ left: rail.current.clientWidth * 0.85 * dir, behavior: 'smooth' });
  return (
    <section className="section rail-section">
      <div className="container">
        <div className="section-head">
          <h2>{title}</h2>
          <div className="rail-ctrl">
            {href && <Link className="link-arrow" href={href}>{t('home.see.all')} <Icon name="arrow" /></Link>}
            <button className="round-btn" type="button" onClick={() => scroll(-1)} aria-label="←"><Icon name="left" /></button>
            <button className="round-btn" type="button" onClick={() => scroll(1)} aria-label="→"><Icon name="right" /></button>
          </div>
        </div>
      </div>
      <div className="rail" id={id} ref={rail}>{items.map(x => <ListingCard key={x.id} item={x} />)}</div>
    </section>
  );
}
