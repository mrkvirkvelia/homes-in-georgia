// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import LegacyView from '@/components/LegacyView';
import { loadRequest, applyRequest } from '@/lib/server';
import { loadingView } from '@/legacy/components.js';

export const metadata: Metadata = { title: 'Saved · Homes in Georgia', robots: { index: false } };

// Favourites live in the visitor's browser (localStorage), so the page is filled in there.
export default async function Favorites() {
  applyRequest(await loadRequest());
  return <LegacyView kind="favorites" html={loadingView()} />;
}
