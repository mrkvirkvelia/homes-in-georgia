// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Catalog from '@/components/Catalog';
import Soon from '@/components/Soon';
import ErrorView from '@/components/ErrorView';
import { getRequest } from '@/lib/server';
import { isService } from '@/lib/config';
import { itemsFor } from '@/lib/filters';

type Props = { params: Promise<{ service: string }> };
const known = (s: string) => s === 'all' || isService(s);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { service } = await params;
  if (!known(service)) return {};
  const { fmt } = await getRequest();
  const title = `${fmt.t('svc.' + service)} · Homes in Georgia`;
  return { title, alternates: { canonical: `/${service}` }, openGraph: { title } };
}

export default async function CatalogPage({ params }: Props) {
  const { service } = await params;
  if (!known(service)) notFound();
  const { feed, fmt, live } = await getRequest();
  if (!feed) return <ErrorView />;
  if (service !== 'all' && isService(service) && !live.includes(service)) return <Soon service={service} fmt={fmt} live={live} />;
  // key: another direction starts with fresh state (search text, sheet, page of the list).
  return <Catalog key={service} serviceId={service} items={itemsFor(feed.items, service)} />;
}
