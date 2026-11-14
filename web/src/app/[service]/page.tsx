// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import LegacyView from '@/components/LegacyView';
import { loadRequest, applyRequest } from '@/lib/server';
import { SERVICES } from '@/legacy/config.js';
import { t } from '@/legacy/i18n.js';
import { parseFilters } from '@/legacy/store.js';
import { catalogMarkup } from '@/legacy/pages/catalog.js';
import { soonMarkup } from '@/legacy/pages/misc.js';
import { errorView } from '@/legacy/components.js';

type Props = { params: Promise<{ service: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };
const known = (s: string) => s === 'all' || s in SERVICES;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { service } = await params;
  if (!known(service)) return {};
  const r = await loadRequest();
  applyRequest(r);
  const title = `${t('svc.' + service)} · Homes in Georgia`;
  return { title, alternates: { canonical: `/${service}` }, openGraph: { title } };
}

export default async function Catalog({ params, searchParams }: Props) {
  const { service } = await params;
  if (!known(service)) notFound();
  const q = new URLSearchParams();
  Object.entries(await searchParams).forEach(([k, v]) => { if (typeof v === 'string') q.set(k, v); });
  const r = await loadRequest();
  applyRequest(r);
  if (!r.data) return <LegacyView key={service} kind="catalog" arg={service} html={errorView()} />;
  const live = service === 'all' || !!(SERVICES as Record<string, { live?: boolean }>)[service].live;
  const html = live ? catalogMarkup(r.data, service, parseFilters(q), { ssr: true }) : soonMarkup(service);
  return <LegacyView key={service} kind={live ? 'catalog' : 'soon'} arg={service} html={html} />;
}
