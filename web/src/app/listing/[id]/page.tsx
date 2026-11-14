// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import LegacyView from '@/components/LegacyView';
import { loadRequest, applyRequest } from '@/lib/server';
import { fetchListing } from '@/lib/api';
import { listingMarkup } from '@/legacy/pages/listing.js';
import { listingTitle, facts, errorView } from '@/legacy/components.js';
import { priceLabel, sqmPrice } from '@/legacy/store.js';
import { placeName } from '@/legacy/places.js';
import { SITE_URL } from '@/legacy/config.js';

type Props = { params: Promise<{ id: string }> };
const abs = (p: string) => (p.startsWith('http') ? p : SITE_URL + p);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const [r, x] = await Promise.all([loadRequest(), fetchListing(decodeURIComponent(id)).catch(() => null)]);
  if (!x) return { title: 'Homes in Georgia' };
  applyRequest(r);
  const p = priceLabel(x);
  const title = `${listingTitle(x)} · ${p.main}${p.period ? ' ' + p.period : ''} · Homes in Georgia`;
  const where = [placeName(x.district), x.metro ? placeName(x.metro as string) : ''].filter(Boolean).join(' · ');
  const description = [facts(x).join(' · '), sqmPrice(x), where, (x.description || '').replace(/\s+/g, ' ').slice(0, 160)].filter(Boolean).join(' · ');
  const images = (x.photos || []).slice(0, 4).map(abs);
  return {
    title, description,
    alternates: { canonical: `/listing/${x.id}` },
    openGraph: { type: 'website', title, description, url: `/listing/${x.id}`, images },
    twitter: { card: 'summary_large_image', title, description, images: images.slice(0, 1) },
  };
}

export default async function Listing({ params }: Props) {
  const { id } = await params;
  const [r, x] = await Promise.all([loadRequest(), fetchListing(decodeURIComponent(id)).catch(() => undefined)]);
  if (x === null) notFound();
  applyRequest(r);
  if (!x || !r.data) return <LegacyView key={id} kind="listing" arg={id} html={errorView()} />;
  return <LegacyView key={x.id} kind="listing" arg={x.id} detail={x} html={listingMarkup(r.data, x)} />;
}
