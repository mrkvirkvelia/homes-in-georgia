// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import Favorites from '@/components/Favorites';

export const metadata: Metadata = { title: 'Saved · Homes in Georgia', robots: { index: false } };

// Favourites live in the visitor's browser (localStorage), so the page is filled in there.
export default function FavoritesPage() {
  return <Favorites />;
}
