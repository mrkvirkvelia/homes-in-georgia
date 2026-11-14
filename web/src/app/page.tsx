// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import Link from 'next/link';
import { Icon } from '@/components/Icon';
import Rail from '@/components/Rail';
import RecentRail from '@/components/RecentRail';
import Finder, { type FinderTab } from '@/components/Finder';
import ErrorView from '@/components/ErrorView';
import { getRequest } from '@/lib/server';
import { CONTACT, GROUPS, SERVICES, telegramHref, type GroupId } from '@/lib/config';
import { countBy, itemsFor, publishedWithin, searchText, type Row } from '@/lib/filters';
import { thumb } from '@/lib/photos';
import type { Feed, Item, ServiceId } from '@/lib/types';
import type { Fmt } from '@/lib/format';

// Finder tabs: live directions only; cars open car rental (sale is one tab away there).
const FINDER: ServiceId[] = ['rent', 'sale', 'commercial', 'daily', 'car-rent'];

/** Budget steps from the real price distribution of a service (rounded quantiles). */
function budgets(pool: Item[]): number[] {
  const prices = pool.map(x => x.price_usd).filter((v): v is number => !!v).sort((a, b) => a - b);
  if (prices.length < 4) return [];
  const nice = (v: number) => { const p = 10 ** Math.max(1, Math.floor(Math.log10(v)) - 1); return Math.round(v / p) * p; };
  return [...new Set([0.25, 0.5, 0.7, 0.85, 0.95].map(q => nice(prices[Math.floor(q * (prices.length - 1))])))];
}

function finderTab(feed: Feed, service: ServiceId): FinderTab {
  const pool = itemsFor(feed.items, service);
  const isCar = SERVICES[service].group === 'auto';
  return {
    service, icon: SERVICES[service].icon,
    rows: pool.map((x): Row => ({ text: searchText(x), district: x.district, price_usd: x.price_usd, rooms: x.rooms, pets: x.pets })),
    districts: countBy(pool, 'district').slice(0, 16),
    steps: budgets(pool),
    period: pool.find(x => x.period)?.period,
    rooms: !isCar && service !== 'commercial' && pool.some(x => x.rooms != null),
    pets: service === 'rent' && pool.some(x => x.pets),
  };
}

/** Home page entrance: one big tile per space with the entry price and the offers of this week. */
function GateTile({ service, i, feed, fmt, live }: { service: ServiceId; i: number; feed: Feed; fmt: Fmt; live: boolean }) {
  const { t } = fmt;
  const pool = itemsFor(feed.items, service);
  const photo = pool.filter(x => x.photos?.length).sort((a, b) => b.ts - a.ts)[0]?.photos?.[0];
  const min = Math.min(...pool.map(x => x.price_usd).filter((v): v is number => !!v));
  const period = pool.find(x => x.period)?.period;
  const week = publishedWithin(pool, 7);
  const count = feed.counts?.[service] || 0;
  return (
    <Link role="listitem" className={`gate-tile${photo ? '' : ' no-photo'}${live ? '' : ' soon'}`} href={`/${service}`} style={{ '--d': `${i * 60}ms` } as React.CSSProperties} prefetch={false}>
      {photo && <img src={thumb(photo)} alt="" {...(i < 2 ? { fetchPriority: 'high' as const } : { loading: 'lazy' as const })} />}
      <span className="gate-ico"><Icon name={SERVICES[service].icon} /></span>
      <span className="gate-text"><b>{t('svc.' + service + '.short')}</b>
        {(Number.isFinite(min) || week > 0) && <span className="gate-hook">
          {Number.isFinite(min) ? t('home.gate.from', fmt.compactMoney(min) + (period ? ' ' + t('period.' + period) : '')) : ''}
          {week > 0 && <span className="gate-new">{t('home.gate.week', week)}</span>}
        </span>}
        <small>{t('svc.' + service + '.desc')}</small></span>
      <span className="gate-meta"><em>{live ? t('cat.count', count) : t('svc.soon')}</em><Icon name="arrow" /></span>
    </Link>
  );
}

export default async function Home() {
  const { feed, fmt, live } = await getRequest();
  if (!feed) return <ErrorView />;
  const { t } = fmt;
  const fresh = (s: ServiceId) => itemsFor(feed.items, s).sort((a, b) => b.ts - a.ts).filter(x => x.photos?.length).slice(0, 12);
  const districts = countBy(feed.items, 'district');
  const districtPhoto = (d: string) => feed.items.find(x => x.district === d && x.photos?.length)?.photos?.[0];
  const heroPhoto = (fresh('rent')[3] || fresh('rent')[0])?.photos?.[0];
  const tabs = FINDER.filter(s => live.includes(s)).map(s => finderTab(feed, s));
  const allServices = (Object.values(GROUPS)).flatMap(g => g.services);

  return (
    <>
      <section className="gate v-cards on-aurora">
        <div className="gate-bg bg-aurora" aria-hidden="true"><i /><i /><i /><i /></div>
        <div className="container">
          <h1 className="gate-title">{t('home.gate.title')}</h1>
          {(Object.entries(GROUPS) as [GroupId, (typeof GROUPS)[GroupId]][]).map(([grp, gr]) => (
            <div key={grp} className="gate-group">
              <div className="gate-group-head"><h2>{t('group.' + grp)}</h2><Link className="link-arrow" href={`/${grp === 'realty' ? 'all' : gr.services[0]}`} prefetch={false}>{t('home.see.all')} <Icon name="arrow" /></Link></div>
              <div className="gate-grid" role="list">{gr.services.map((s, i) => <GateTile key={s} service={s} i={i} feed={feed} fmt={fmt} live={live.includes(s)} />)}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="section finder-section">
        <div className="container"><Finder tabs={tabs} total={feed.items.length} photo={heroPhoto} /></div>
      </section>

      <RecentRail />
      {allServices.filter(s => live.includes(s)).map(s => <Rail key={s} id={'rail-' + s} title={t('home.fresh.' + s)} items={fresh(s)} href={'/' + s} />)}

      <section className="section">
        <div className="container">
          <div className="section-head"><div><h2>{t('home.districts.title')}</h2><p>{t('home.districts.lead')}</p></div></div>
          <div className="districts">
            {districts.slice(0, 8).map(([d, n], i) => {
              const photo = districtPhoto(d);
              return (
                <Link key={d} className={`district${i === 0 ? ' big' : ''}`} href={`/all?district=${encodeURIComponent(d)}`} prefetch={false}>
                  {photo && <img src={thumb(photo)} alt="" loading="lazy" />}
                  <span><b>{fmt.place(d)}</b><em>{t('cat.count', n)}</em></span>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="why">
            {([['shield', 1], ['send', 3], ['star', 4]] as const).map(([ic, n]) => (
              <div key={n} className="why-item"><span><Icon name={ic} /></span><div><h3>{t(`home.why.${n}.t`)}</h3><p>{t(`home.why.${n}.d`)}</p></div></div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="owners">
            <div><h2>{t('home.owners.title')}</h2><p>{t('home.owners.lead')}</p></div>
            <a className="btn btn-light btn-lg" href={telegramHref(CONTACT.telegram)} target="_blank" rel="noopener"><Icon name="send" /><span>{t('home.owners.cta')}</span></a>
          </div>
        </div>
      </section>
    </>
  );
}
