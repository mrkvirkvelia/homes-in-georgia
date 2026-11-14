// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Listing card inside a map popup.
import Link from 'next/link';
import { useFmt } from './Providers';
import { thumb } from '@/lib/photos';
import type { Item } from '@/lib/types';

export default function MapCard({ item: x }: { item: Item }) {
  const fmt = useFmt();
  const p = fmt.priceLabel(x);
  return (
    <Link className="map-card" href={`/listing/${x.id}`}>
      {x.photos?.[0] && <img src={thumb(x.photos[0])} alt="" />}
      <div><b>{p.main} <small>{[p.period, fmt.sqmPrice(x)].filter(Boolean).join(' · ')}</small></b><span>{fmt.title(x)}</span><em>{fmt.facts(x).join(' · ')}</em></div>
    </Link>
  );
}
