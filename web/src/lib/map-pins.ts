// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Marker, DivIcon } from 'leaflet';
import type { LeafletLib } from './leaflet';
import { listingTitle } from './format';
import type { Item } from './types';

/** Price pill marker of the catalogue and listing maps. */
export const pricePin = (L: LeafletLib, x: Item, label: string, onClick?: () => void): Marker => {
  const icon: DivIcon = L.divIcon({ className: 'pin', html: `<span>${label.replace(/[&<>"]/g, c => `&#${c.charCodeAt(0)};`)}</span>`, iconSize: undefined });
  const m = L.marker([x.lat!, x.lon!], { icon, keyboard: true, title: listingTitle(x) });
  if (onClick) m.on('click', onClick);
  return m;
};
