// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import LegacyView from '@/components/LegacyView';
import { loadRequest, applyRequest } from '@/lib/server';
import { t } from '@/legacy/i18n.js';

export const metadata: Metadata = {
  title: 'Map · Homes in Georgia',
  description: 'Map of every Homes in Georgia listing in Tbilisi: rentals, sales, commercial, daily stays and cars. Filter by price, rooms and district and share the link.',
  alternates: { canonical: '/map' },
  openGraph: { title: 'Homes in Georgia — map of listings', description: 'Rentals, sales, commercial property and cars in Tbilisi on one map.' },
};

// The map is drawn in the browser (Leaflet). Until then: a placeholder, and no footer under it.
export default async function MapPage() {
  const r = await loadRequest();
  applyRequest(r);
  const html = `<style>.footer{display:none}</style><div class="container page-pad"><h1 class="sr-only">${t('map.title')}</h1><p class="loading-line" role="status">${t('loading')}</p></div>`;
  return <LegacyView kind="map" html={html} />;
}
