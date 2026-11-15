// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { Icon } from '@/components/Icon';
import Rail from '@/components/Rail';
import ErrorView from '@/components/ErrorView';
import { PriceCard, StickyBar } from '@/components/ListingSide';
import { Amenities, BackButton, Description, Gallery, LocationMap, RecordView, ShareFav } from '@/components/ListingParts';
import { fetchListing, findInFeed } from '@/lib/api';
import { getRequest } from '@/lib/server';
import { AMENITY_ORDER, SERVICES, SITE_URL } from '@/lib/config';
import type { Fmt } from '@/lib/format';
import type { Feed, Item } from '@/lib/types';

type Props = { params: Promise<{ id: string }> };
const abs = (p: string) => (p.startsWith('http') ? p : SITE_URL + p);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const [{ fmt }, x] = await Promise.all([getRequest(), fetchListing(decodeURIComponent(id)).catch(() => null)]);
  if (!x) return { title: 'Homes in Georgia' };
  const p = fmt.priceLabel(x);
  const title = `${fmt.title(x)} · ${p.main}${p.period ? ' ' + p.period : ''} · Homes in Georgia`;
  const where = [fmt.place(x.district), x.metro ? fmt.place(x.metro) : ''].filter(Boolean).join(' · ');
  const description = [fmt.facts(x).join(' · '), fmt.sqmPrice(x), where, (x.description || '').replace(/\s+/g, ' ').slice(0, 160)].filter(Boolean).join(' · ');
  const images = (x.photos || []).slice(0, 4).map(abs);
  return {
    title, description,
    alternates: { canonical: `/listing/${x.id}` },
    openGraph: { type: 'website', title, description, url: `/listing/${x.id}`, images },
    twitter: { card: 'summary_large_image', title, description, images: images.slice(0, 1) },
  };
}

function similar(feed: Feed, x: Item): Item[] {
  const p = x.price_usd || 0;
  return feed.items
    .filter(y => y.id !== x.id && y.service === x.service && y.photos?.length)
    .map(y => ({ y, s: (y.district === x.district ? 0 : 1) + (p && y.price_usd ? Math.abs(Math.log(y.price_usd / p)) : 1) + (y.rooms === x.rooms ? 0 : 0.5) }))
    .sort((a, b) => a.s - b.s)
    .slice(0, 10)
    .map(a => a.y);
}

type Row = [string, string, string | number];
function Facts({ rows }: { rows: Row[] }) {
  return <div className="facts">{rows.map(([ic, k, v]) => <div key={k} className="fact"><Icon name={ic} /><span>{k}</span><b>{v}</b></div>)}</div>;
}

function factRows(x: Item, fmt: Fmt): Row[] {
  const { t, num } = fmt;
  const rows: Row[] = x.kind === 'car' ? [
    ['calendar', t('l.year'), x.year || ''],
    ['car', t('f.body'), x.body ? t('body.' + x.body) : ''],
    ['users', t('l.seats'), x.seats || ''],
    ['pin', t('l.pickup'), x.pickup || ''],
    ['gauge', t('l.mileage'), x.mileage ? `${num(x.mileage)} km` : ''],
    ['sliders', t('f.gearbox'), x.gearbox ? t('gearbox.' + x.gearbox) : ''],
    ['flame', t('f.fuel'), x.fuel ? t('fuel.' + x.fuel) : ''],
  ] : [
    ['bed', t('l.rooms'), x.rooms != null ? (x.rooms === 0 ? t('f.studio') : x.rooms) : ''],
    ['area', t('l.area'), x.area ? `${num(x.area)} m²` : ''],
    ['layers', t('l.floor'), x.floor ? (x.floors ? `${x.floor} / ${x.floors}` : x.floor) : ''],
    ['home', t('l.kind'), t(x.type ? 'type.' + x.type : 'kind.' + x.kind) + (x.service === 'commercial' && x.deal ? ' · ' + t('deal.' + x.deal) : '')],
    ['building', t('l.building'), x.building ? t('building.' + x.building) : ''],
    ['sparkles', t('l.bathrooms'), x.bathrooms || ''],
    ['brush', t('l.condition'), x.condition ? t('cond.' + x.condition) : ''],
    ['flame', t('l.heating'), x.heating ? t('heat.' + x.heating) : ''],
    ['calendar', t('l.completion'), x.completion || ''],
  ];
  return rows.filter(r => r[2] !== '');
}

export default async function ListingPage({ params }: Props) {
  const { id: raw } = await params;
  const id = decodeURIComponent(raw);
  const [{ feed, fmt }, detail] = await Promise.all([getRequest(), fetchListing(id).catch(() => undefined)]);
  if (detail === null) notFound();
  if (!detail || !feed) return <ErrorView />;
  // The feed item plus the detail record (full description, video).
  const x: Item = { ...findInFeed(feed, id), ...detail };
  const { t } = fmt;
  const svc = SERVICES[x.service];
  const title = fmt.title(x);
  const agent = x.agent?.telegram || x.agent?.name || '';
  const amenities = AMENITY_ORDER.filter(a => x.amenities?.includes(a));
  const factList = factRows(x, fmt);
  const dep = fmt.depositUsd(x);
  const terms: Row[] = ([
    ['calendar', t('l.term'), x.months?.length ? t('l.term.value', x.months) : ''],
    ['paw', t('l.pets'), x.pets ? t('pets.' + x.pets) : ''],
    ['users', t('l.tenants'), x.tenants ? t('l.tenants.value', x.tenants) : ''],
    ['key', t('l.deposit'), dep ? fmt.money(dep) : ''],
  ] as Row[]).filter(r => r[2]);

  return (
    <article className="listing" data-listing={x.id} data-service={x.service} data-agent={agent}>
      <RecordView item={x} />
      <div className="container">
        <BackButton service={x.service} />
        <nav className="crumbs" aria-label="breadcrumbs"><Link href="/">{t('nav.home')}</Link><Icon name="right" /><Link href={`/${x.service}`}>{t('svc.' + x.service + '.short')}</Link>
          {x.district && <><Icon name="right" /><Link href={`/${x.service}?district=${encodeURIComponent(x.district)}`}>{fmt.place(x.district)}</Link></>}</nav>
        <header className="l-head">
          <div>
            <div className="l-badges">
              <span className="badge badge-soft"><Icon name={svc.icon} />{t('svc.' + x.service + '.short')}</span>
              {x.exclusive && <span className="badge badge-accent">{t('card.exclusive')}</span>}
            </div>
            <h1>{title}</h1>
            {x.kind !== 'car' && <p className="l-addr"><Icon name="pin" />{[x.title !== title ? x.title : '', fmt.place(x.district)].filter(Boolean).join(' · ') || t('city')}{x.metro && <span className="metro"><Icon name="metro" />{fmt.place(x.metro)}</span>}</p>}
          </div>
          <div className="l-actions">
            {x.video && <a className="btn btn-outline" href={x.video} target="_blank" rel="noopener"><Icon name="external" /><span>Video</span></a>}
            <ShareFav item={x} />
          </div>
        </header>
        <Gallery photos={x.photos || []} title={title} />
        <div className="l-grid">
          <div className="l-main">
            {factList.length > 0 && <section className="l-sec"><h2>{t('l.facts')}</h2><Facts rows={factList} /></section>}
            {x.description && <section className="l-sec"><h2>{t('l.about')}</h2><Description text={x.description} /></section>}
            {amenities.length > 0 && <section className="l-sec"><h2>{t('l.amenities')}</h2><Amenities items={amenities} /></section>}
            {terms.length > 0 && <section className="l-sec"><h2>{t('l.terms')}</h2><Facts rows={terms} /></section>}
            {Number.isFinite(x.lat) && Number.isFinite(x.lon) && <section className="l-sec"><h2>{t('l.location')}</h2><LocationMap item={x} />{x.approx && <p className="l-approx">{t('l.location.approx')}</p>}</section>}
            <p className="l-meta">{t('l.id')}: {x.id} · {t('l.published')}: {fmt.ago(x.published_at)}
              {x.post_url && <> · <a href={x.post_url} target="_blank" rel="noopener">{t('l.source')} <Icon name="external" /></a></>}</p>
          </div>
          <aside className="l-side"><PriceCard item={x} /></aside>
        </div>
      </div>
      <Rail id="rail-similar" title={t('l.similar')} items={similar(feed, x)} href={'/' + x.service + (x.district ? '?district=' + encodeURIComponent(x.district) : '')} />
      <StickyBar item={x} />
    </article>
  );
}
