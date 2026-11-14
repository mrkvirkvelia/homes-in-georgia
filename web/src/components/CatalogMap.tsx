// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Desktop split view of a catalogue: a Leaflet map with price-pill markers and clustering, in sync with the list
// (hovering a card lights its marker). Loaded from unpkg when the map view is first shown.
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Map as LMap, Marker, MarkerClusterGroup } from 'leaflet';
import MapCard from './MapCard';
import { useFmt } from './Providers';
import { MAP_CENTER } from '@/lib/config';
import { brandMap, hasPoint, loadLeaflet, mapTiler, type LeafletLib } from '@/lib/leaflet';
import { pricePin } from '@/lib/map-pins';
import type { Item } from '@/lib/types';

export default function CatalogMap({ items, hotId }: { items: Item[]; hotId: string | null }) {
  const fmt = useFmt();
  const el = useRef<HTMLDivElement>(null);
  const lib = useRef<{ L: LeafletLib; map: LMap; layer: MarkerClusterGroup } | null>(null);
  const markers = useRef(new Map<string, Marker>());
  const [ready, setReady] = useState(false);
  const [popup, setPopup] = useState<{ x: Item; node: HTMLElement } | null>(null);
  const tRef = useRef(fmt.t);
  useEffect(() => { tRef.current = fmt.t; });

  useEffect(() => {
    let alive = true;
    let map: LMap | undefined;
    loadLeaflet().then(L => {
      if (!alive || !el.current) return;
      map = L.map(el.current, { zoomControl: false, scrollWheelZoom: true, dragging: true, attributionControl: true }).setView(MAP_CENTER, 12);
      L.control.zoom({ position: 'bottomright' }).addTo(map);
      brandMap(map);
      const streets = mapTiler(L, 'streets-v2').addTo(map);
      L.control.layers({ [tRef.current('map.streets')]: streets, [tRef.current('map.satellite')]: mapTiler(L, 'hybrid', 'jpg') }, undefined, { position: 'topright' }).addTo(map);
      const layer = L.markerClusterGroup({
        showCoverageOnHover: false, maxClusterRadius: 48, spiderfyOnMaxZoom: true,
        iconCreateFunction: c => L.divIcon({ html: `<span>${c.getChildCount()}</span>`, className: 'cluster', iconSize: [40, 40] }),
      }).addTo(map);
      map.on('popupclose', () => setPopup(null));
      lib.current = { L, map, layer };
      setTimeout(() => map?.invalidateSize(), 0);
      setReady(true);
    }).catch(() => {});
    const pins = markers.current;
    return () => { alive = false; lib.current = null; pins.clear(); map?.remove(); };
  }, []);

  // Markers follow the list; the map fits the found listings.
  useEffect(() => {
    const l = lib.current;
    if (!ready || !l) return;
    const { L, map, layer } = l;
    layer.clearLayers();
    markers.current.clear();
    const pts = items.filter(hasPoint);
    pts.forEach(x => {
      const m = pricePin(L, x, x.price_usd ? fmt.compactMoney(x.price_usd) : '•');
      m.bindPopup(() => { const node = document.createElement('div'); setPopup({ x, node }); return node; }, { closeButton: false, className: 'pop', offset: [0, -6], maxWidth: 280 });
      markers.current.set(x.id, m);
      layer.addLayer(m);
    });
    map.invalidateSize(); // the pane may have just appeared
    if (pts.length) map.fitBounds(L.latLngBounds(pts.map(x => [x.lat!, x.lon!] as [number, number])), { padding: [40, 40], maxZoom: 15 });
  }, [ready, items, fmt]);

  // List ⇄ map highlighting.
  useEffect(() => {
    const m = hotId ? markers.current.get(hotId) : undefined;
    const node = m?.getElement();
    if (!m || !node) return;
    node.classList.add('hot');
    m.setZIndexOffset(1000);
    return () => { node.classList.remove('hot'); m.setZIndexOffset(0); };
  }, [hotId, ready, items]);

  return <>
    <div className="map" id="cat-map" ref={el} />
    {popup && createPortal(<MapCard item={popup.x} />, popup.node)}
  </>;
}
