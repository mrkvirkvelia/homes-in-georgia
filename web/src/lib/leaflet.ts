// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Leaflet + MarkerCluster are loaded from unpkg when a map is first needed (as before), MapTiler tiles.
/// <reference types="leaflet.markercluster" />
import type * as Leaflet from 'leaflet';
import { MAPTILER_KEY } from './config';
import { logoSrc } from '@/components/Icon';

export type LeafletLib = typeof Leaflet;
declare global { interface Window { L?: LeafletLib } }

const LEAFLET = 'https://unpkg.com/leaflet@1.9.4/dist/';
const CLUSTER = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/';

let loading: Promise<LeafletLib> | undefined;
export function loadLeaflet(): Promise<LeafletLib> {
  const css = (href: string) => new Promise<void>(res => { const l = Object.assign(document.createElement('link'), { rel: 'stylesheet', href, onload: () => res(), onerror: () => res() }); document.head.append(l); });
  const js = (src: string) => new Promise<void>((res, rej) => { const s = Object.assign(document.createElement('script'), { src, onload: () => res(), onerror: rej }); document.head.append(s); });
  loading ??= Promise.all([css(LEAFLET + 'leaflet.css'), css(CLUSTER + 'MarkerCluster.css')])
    .then(() => js(LEAFLET + 'leaflet.js'))
    .then(() => js(CLUSTER + 'leaflet.markercluster.js'))
    .then(() => window.L!)
    .catch(err => { loading = undefined; throw err; });
  return loading;
}

const MT_ATTRIBUTION = '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener">&copy; MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">&copy; OpenStreetMap</a>';
/** Our logo sits beside the required map credit, in the same corner of every map. */
export const brandMap = (map: Leaflet.Map) => map.attributionControl.setPrefix(`<img class="logo map-logo" src="${logoSrc()}" alt="Homes in Georgia" width="132" height="40">`);
export const mapTiler = (L: LeafletLib, style: string, ext = 'png') => L.tileLayer(`https://api.maptiler.com/maps/${style}/256/{z}/{x}/{y}{r}.${ext}?key=${MAPTILER_KEY}`, {
  maxZoom: 20, attribution: MT_ATTRIBUTION, crossOrigin: true,
});

// "Where am I" button: a blue dot with an accuracy ring that follows the visitor.
// The position stays in the browser; nothing about it is sent anywhere.
const LOCATE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 4 3.5 10.6l7 2.4 2.4 7Z"/></svg>';
export function addLocate(L: LeafletLib, map: Leaflet.Map, t: (key: string) => string, notify: (text: string) => void) {
  let watch: number | null = null, dot: Leaflet.Marker | null = null, ring: Leaflet.Circle | null = null, first = true;
  const stop = (btn: HTMLElement) => {
    if (watch !== null) navigator.geolocation.clearWatch(watch);
    watch = null; first = true;
    dot?.remove(); ring?.remove(); dot = ring = null;
    btn.classList.remove('on', 'busy');
    btn.setAttribute('aria-pressed', 'false');
  };
  const start = (btn: HTMLElement) => {
    if (!('geolocation' in navigator)) return notify(t('map.locate.fail'));
    btn.classList.add('busy');
    btn.setAttribute('aria-pressed', 'true');
    watch = navigator.geolocation.watchPosition(pos => {
      const at: [number, number] = [pos.coords.latitude, pos.coords.longitude];
      const r = Math.min(pos.coords.accuracy || 0, 3000);
      if (!dot || !ring) {
        ring = L.circle(at, { radius: r, interactive: false, className: 'me-ring', weight: 1 }).addTo(map);
        dot = L.marker(at, { interactive: false, keyboard: false, zIndexOffset: 200000,
          icon: L.divIcon({ className: 'me-dot', html: '<i></i>', iconSize: [22, 22] }) }).addTo(map);
      } else { dot.setLatLng(at); ring.setLatLng(at).setRadius(r); }
      btn.classList.remove('busy'); btn.classList.add('on');
      if (first) { first = false; map.flyTo(at, Math.max(map.getZoom(), 15), { duration: .8 }); }
    }, err => {
      // Once the dot is shown, a phone that stands still or briefly loses signal reports timeouts; keep the last position.
      if (dot && err.code !== 1) return;
      stop(btn);
      notify(t(err.code === 1 ? 'map.locate.denied' : 'map.locate.fail'));
    }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
  };
  let stopFn: (() => void) | null = null;
  const Locate = L.Control.extend({
    options: { position: 'bottomright' },
    onAdd() {
      const box = L.DomUtil.create('div', 'leaflet-bar leaflet-control map-locate');
      const btn = L.DomUtil.create('a', '', box);
      btn.href = '#';
      btn.setAttribute('role', 'button');
      btn.title = t('map.locate');
      btn.setAttribute('aria-label', t('map.locate'));
      btn.setAttribute('aria-pressed', 'false');
      btn.innerHTML = LOCATE_ICON;
      L.DomEvent.disableClickPropagation(box);
      L.DomEvent.on(btn, 'click', e => { L.DomEvent.preventDefault(e); if (watch === null) start(btn); else stop(btn); });
      stopFn = () => stop(btn);
      return box;
    },
    onRemove() { stopFn?.(); },
  });
  return new Locate().addTo(map);
}

export const hasPoint = (x: { lat?: number; lon?: number }): x is { lat: number; lon: number } => Number.isFinite(x.lat) && Number.isFinite(x.lon);

/** Phones: a double tap on the map zooms in one step towards the tapped point. Taps on pins, clusters and controls keep their own behaviour. */
export function doubleTapZoom(L: LeafletLib, map: Leaflet.Map) {
  const el = map.getContainer();
  let lastTime = 0, lastX = 0, lastY = 0, startX = 0, startY = 0, single = false;
  el.addEventListener('touchstart', e => {
    single = e.touches.length === 1;
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
  }, { passive: true });
  el.addEventListener('touchmove', e => {
    const p = e.touches[0];
    if (e.touches.length > 1 || Math.hypot(p.clientX - startX, p.clientY - startY) > 10) single = false;
  }, { passive: true });
  el.addEventListener('touchend', e => {
    const p = e.changedTouches[0];
    if (!single || e.touches.length || (e.target as Element).closest('.leaflet-marker-icon, .leaflet-control')) { lastTime = 0; return; }
    const now = Date.now();
    if (now - lastTime < 350 && Math.hypot(p.clientX - lastX, p.clientY - lastY) < 30) {
      e.preventDefault();
      lastTime = 0;
      map.setZoomAround(L.DomEvent.getMousePosition(p as unknown as MouseEvent, el), map.getZoom() + 1);
    } else {
      lastTime = now;
      lastX = p.clientX;
      lastY = p.clientY;
    }
  }, { passive: false });
}
