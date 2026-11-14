// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import MapApp from '@/components/MapApp';
import ErrorView from '@/components/ErrorView';
import { getRequest } from '@/lib/server';

export const metadata: Metadata = {
  title: 'Map · Homes in Georgia',
  description: 'Map of every Homes in Georgia listing in Tbilisi: rentals, sales, commercial, daily stays and cars. Filter by price, rooms and district and share the link.',
  alternates: { canonical: '/map' },
  openGraph: { title: 'Homes in Georgia — map of listings', description: 'Rentals, sales, commercial property and cars in Tbilisi on one map.' },
};

// The map is drawn in the browser (Leaflet); the controls and the counts come with the page.
export default async function MapPage() {
  const { feed } = await getRequest();
  return feed ? <MapApp items={feed.items} /> : <ErrorView />;
}
