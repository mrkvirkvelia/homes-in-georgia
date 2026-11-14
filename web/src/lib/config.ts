// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Single place for business configuration: services, contacts, channels. Copy lives in i18n.
import type { ServiceId, Item } from './types';

export const SITE_URL = 'https://hge.ge';

export const CONTACT = { telegram: 'David_Tibelashvili', phone: '+995 599 20 67 16' };

// Our own site analytics (apps-script/site-analytics.gs). Empty = switched off.
export const ANALYTICS_URL = 'https://script.google.com/macros/s/AKfycbwPOZbRvKr2D1j61bn-fRwVeRjb-tNH6X31XNKoU5gKXQ_PcU6Ad6YFn1n7kxAKFw7voA/exec';

// Public Telegram channel of every direction.
export const CHANNELS: Record<ServiceId, string> = {
  rent: 'rent_tbilisi_ge',
  sale: 'homesingeorgia',
  commercial: 'commercialingeorgia',
  daily: 'dayrentingeorgia',
  new: 'DevelopmentIngeorgia',
  'car-rent': 'CarsRentInGeorgia',
  'car-sale': 'CarsSaleInGeorgia',
};

export const OFFICE_MAP = 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent('Stamba, 14 Merab Kostava St, Tbilisi');

export type BrandName = 'instagram' | 'facebook' | 'tiktok' | 'youtube' | 'threads';
export const SOCIALS: { brand: string; accounts: { icon: BrandName; label: string; name: string; handle: string; href: string }[] }[] = [
  { brand: 'Homes in Georgia', accounts: [
    { icon: 'instagram', label: 'soc.instagram', name: 'Instagram', handle: '@homesingeorgia', href: 'https://www.instagram.com/homesingeorgia/' },
    { icon: 'facebook', label: 'soc.facebook', name: 'Facebook', handle: 'Homes in Georgia', href: 'https://www.facebook.com/share/1DiStYPSGc/' },
  ] },
  { brand: 'Rent in Tbilisi', accounts: [
    { icon: 'instagram', label: 'soc.instagram', name: 'Instagram', handle: '@rent_in_tbilisi', href: 'https://www.instagram.com/rent_in_tbilisi/' },
    { icon: 'instagram', label: 'soc.listing', name: 'Instagram', handle: '@rentintbilisilisting', href: 'https://www.instagram.com/rentintbilisilisting/' },
    { icon: 'facebook', label: 'soc.facebook', name: 'Facebook', handle: 'rentintbilisi.ge', href: 'https://www.facebook.com/rentintbilisi.ge' },
    { icon: 'tiktok', label: 'soc.tiktok', name: 'TikTok', handle: '@rent.in.tbilisi', href: 'https://www.tiktok.com/@rent.in.tbilisi' },
    { icon: 'youtube', label: 'soc.youtube', name: 'YouTube', handle: '@RENTINTBILISI', href: 'https://www.youtube.com/@RENTINTBILISI' },
    { icon: 'threads', label: 'soc.threads', name: 'Threads', handle: '@rent_in_tbilisi', href: 'https://www.threads.com/@rent_in_tbilisi' },
  ] },
];
export const PORTALS = [
  { name: 'Myhome.ge', href: 'https://www.myhome.ge/s/?users=4201800' },
  { name: 'SS.ge', href: 'https://home.ss.ge/ka/udzravi-qoneba/userlist?userId=65aa7435-d32e-40bc-b86b-9d963efbbe77' },
];

export const phoneHref = (phone?: string) => 'tel:' + String(phone || CONTACT.phone).replace(/[^\d+]/g, '');
export const whatsappHref = (phone?: string, text = '') =>
  'https://wa.me/' + String(phone || CONTACT.phone).replace(/\D/g, '') + (text ? '?text=' + encodeURIComponent(text) : '');
/** `text` pre-fills the message in the chat (Telegram's ?text= username-link parameter). */
export const telegramHref = (user?: string, text = '') =>
  'https://t.me/' + String(user || CONTACT.telegram).replace(/^@/, '') + (text ? '?text=' + encodeURIComponent(text) : '');

export type IconName = string;
export interface ServiceDef { group: 'realty' | 'auto'; icon: IconName; filters: string[] }
const REALTY = ['price', 'beds', 'kind', 'area', 'district', 'metro'];
// `filters` lists the filter panel sections of the catalogue. A service is "live" when the feed has offers for it.
export const SERVICES: Record<ServiceId, ServiceDef> = {
  rent: { group: 'realty', icon: 'key', filters: [...REALTY, 'floor', 'floors', 'building', 'condition', 'heating', 'amenities', 'deposit', 'tenants', 'term', 'pets', 'flags'] },
  sale: { group: 'realty', icon: 'tag', filters: [...REALTY, 'floor', 'floors', 'building', 'condition', 'heating', 'amenities', 'ppsqm', 'flags'] },
  commercial: { group: 'realty', icon: 'building', filters: ['price', 'deal', 'area', 'district', 'metro', 'floor', 'floors', 'building', 'condition', 'heating', 'amenities', 'ppsqm', 'deposit', 'term', 'flags'] },
  daily: { group: 'realty', icon: 'moon', filters: ['price', 'beds', 'district', 'metro', 'floor', 'floors', 'heating', 'amenities', 'flags'] },
  new: { group: 'realty', icon: 'crane', filters: ['price', 'beds', 'area', 'district', 'metro', 'condition', 'heating', 'flags'] },
  'car-rent': { group: 'auto', icon: 'car', filters: ['price', 'body', 'gearbox', 'fuel', 'year', 'seats', 'pickup', 'flags'] },
  'car-sale': { group: 'auto', icon: 'gauge', filters: ['price', 'body', 'year', 'mileage', 'gearbox', 'fuel', 'seats', 'pickup', 'flags'] },
};
export const SERVICE_IDS = Object.keys(SERVICES) as ServiceId[];
export const isService = (s: string): s is ServiceId => s in SERVICES;

export const GROUPS = {
  realty: { icon: 'home', services: ['rent', 'sale', 'commercial', 'daily', 'new'] as ServiceId[] },
  auto: { icon: 'car', services: ['car-rent', 'car-sale'] as ServiceId[] },
};
export type GroupId = keyof typeof GROUPS;

/** Pseudo-service of the global search: every real-estate offer. */
export const ALL: ServiceDef = { group: 'realty', icon: 'search', filters: [...REALTY, 'floor', 'floors', 'building', 'condition', 'heating', 'amenities', 'flags'] };
export const serviceOf = (id: string): ServiceDef => (id === 'all' ? ALL : SERVICES[id as ServiceId]);

export const AMENITY_ORDER = ['conditioner', 'wifi', 'dishwasher', 'washer', 'oven', 'microwave', 'stove', 'tv', 'balcony',
  'terrace', 'courtyard', 'elevator', 'parking', 'pool', 'gym', 'fireplace', 'view', 'vacuum', 'storage', 'security', 'generator', 'playground'];
export const FILTER_AMENITIES = ['conditioner', 'wifi', 'tv', 'stove', 'oven', 'microwave', 'dishwasher', 'washer', 'vacuum', 'balcony', 'terrace', 'courtyard', 'elevator', 'parking', 'fireplace', 'storage', 'pool'];

export const MAP_CENTER: [number, number] = [41.7151, 44.8271];
// MapTiler key is public by design (it ships to the browser); it is restricted to the site's domain in the MapTiler dashboard.
export const MAPTILER_KEY = '8rgCgBliYpwKCmMzEVV8';

// Total map: one switch per Telegram channel; the marker icon follows the post's kind; colour = freshness of the post.
export const MAP_CHANNELS: { id: ServiceId; icon: IconName }[] = [
  { id: 'rent', icon: 'key' }, { id: 'daily', icon: 'moon' }, { id: 'sale', icon: 'tag' }, { id: 'commercial', icon: 'kiosk' },
  { id: 'new', icon: 'crane' }, { id: 'car-rent', icon: 'car' }, { id: 'car-sale', icon: 'gauge' },
];
export const KIND_ICONS: Record<string, IconName> = { apartment: 'building', house: 'home', commercial: 'kiosk', land: 'land', car: 'car' };
// homesingeorgia ("homes") and the older sale_in_tbilisi ("sale") are one sale direction.
export const channelOf = (x: Item): string => (x.source === 'homes' ? 'sale' : x.source || x.service);

export const FRESHNESS = [
  { id: 'fresh', maxDays: 5, color: '#2DB87A' },
  { id: 'recent', maxDays: 20, color: '#F3A712' },
  { id: 'old', maxDays: Infinity, color: '#E5532E' },
];
export type Freshness = (typeof FRESHNESS)[number];
export const freshnessOf = (x: Item): Freshness => {
  const days = (Date.now() - (x.ts || 0)) / 864e5;
  return FRESHNESS.find(f => days < f.maxDays)!;
};
