// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// A catalogue (a direction or "all"): search, sort, filter pills and sheet, active filter chips, a growing card list,
// and on desktop a map beside it. The filters live in the URL query (?q=&price=-1500&beds=2…), so every state is a link.
import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Icon } from './Icon';
import ListingCard from './ListingCard';
import FilterSheet from './FilterSheet';
import CatalogMap from './CatalogMap';
import { Empty } from './Empty';
import { useSite } from './Providers';
import { GROUPS, SERVICES, serviceOf } from '@/lib/config';
import {
  RANGE_KEYS, activeCount, applyFilters, filtersToParams, parseFilters, sortItems, toRow, type Filters, type Range,
} from '@/lib/filters';
import { trackSearch } from '@/lib/analytics';
import { useDesktop } from '@/lib/hooks';
import { pageTop, saveEntry, scrollRoot, setPageTop } from '@/lib/scroll';
import { hasPoint } from '@/lib/leaflet';
import type { Fmt } from '@/lib/format';
import type { Item, ServiceId } from '@/lib/types';

const PAGE = 24;

interface Chip { label: string; apply: (f: Filters) => void }

function activeChips(f: Filters, fmt: Fmt): Chip[] {
  const { t, num, compactMoney } = fmt;
  const chips: Chip[] = [];
  const add = (label: string, apply: (f: Filters) => void) => chips.push({ label, apply });
  const span = ([a, b]: Range, format: (v: number) => string) => (a != null && b != null ? `${format(a)} — ${format(b)}` : a != null ? `${t('f.from')} ${format(a)}` : `${t('f.to')} ${format(b as number)}`);
  const isSet = (r: Range) => r[0] != null || r[1] != null;
  const clear = (k: (typeof RANGE_KEYS)[number]) => (x: Filters) => { x[k] = [null, null]; };
  if (isSet(f.price)) add(span(f.price, compactMoney), clear('price'));
  if (isSet(f.area)) add(span(f.area, v => `${Math.round(v)} m²`), clear('area'));
  if (isSet(f.year)) add(span(f.year, v => String(Math.round(v))), clear('year'));
  if (isSet(f.mileage)) add(span(f.mileage, v => `${num(v)} km`), clear('mileage'));
  f.deal.forEach(k => add(t('deal.' + k), x => { x.deal = x.deal.filter(v => v !== k); }));
  f.gearbox.forEach(k => add(t('gearbox.' + k), x => { x.gearbox = x.gearbox.filter(v => v !== k); }));
  f.fuel.forEach(k => add(t('fuel.' + k), x => { x.fuel = x.fuel.filter(v => v !== k); }));
  f.body.forEach(k => add(t('body.' + k), x => { x.body = x.body.filter(v => v !== k); }));
  f.beds.forEach(b => add(b === '0' ? t('f.studio') : t('card.beds', +b) + (b === '4' ? '+' : ''), x => { x.beds = x.beds.filter(v => v !== b); }));
  f.kind.forEach(k => add(t('kind.' + k), x => { x.kind = x.kind.filter(v => v !== k); }));
  f.district.forEach(d => add(fmt.place(d), x => { x.district = x.district.filter(v => v !== d); }));
  if (f.metro) add(fmt.place(f.metro), x => { x.metro = ''; });
  f.building.forEach(k => add(t('building.' + k), x => { x.building = x.building.filter(v => v !== k); }));
  f.condition.forEach(k => add(t('cond.' + k), x => { x.condition = x.condition.filter(v => v !== k); }));
  f.heating.forEach(k => add(t('heat.' + k), x => { x.heating = x.heating.filter(v => v !== k); }));
  f.amen.forEach(k => add(t('am.' + k), x => { x.amen = x.amen.filter(v => v !== k); }));
  if (f.term) add(t('term.' + f.term), x => { x.term = ''; });
  if (isSet(f.floor)) add(t('f.floor') + ' ' + span(f.floor, v => String(Math.round(v))), clear('floor'));
  if (isSet(f.floors)) add(t('f.floors') + ' ' + span(f.floors, v => String(Math.round(v))), clear('floors'));
  if (isSet(f.ppsqm)) add(t('f.ppsqm') + ' ' + span(f.ppsqm, compactMoney), clear('ppsqm'));
  if (isSet(f.deposit)) add(t('f.deposit') + ' ' + span(f.deposit, compactMoney), clear('deposit'));
  if (f.notfirst) add(t('f.notfirst'), x => { x.notfirst = false; });
  if (f.notlast) add(t('f.notlast'), x => { x.notlast = false; });
  if (f.tenants) add(t('f.tenants') + ': ' + f.tenants + (f.tenants === '5' ? '+' : ''), x => { x.tenants = ''; });
  if (f.seats) add(t('f.seats') + ': ' + f.seats, x => { x.seats = ''; });
  if (f.pickup) add(f.pickup, x => { x.pickup = ''; });
  if (f.pets) add(t('f.pets'), x => { x.pets = false; });
  if (f.excl) add(t('f.exclusive'), x => { x.excl = false; });
  return chips;
}

function pillLabel(k: string, f: Filters, fmt: Fmt): [string, boolean] {
  const { t, compactMoney } = fmt;
  const range = (v: Range, format: (n: number) => string) => (v[0] != null && v[1] != null ? `${format(v[0])}–${format(v[1])}` : v[0] != null ? `${t('f.from')} ${format(v[0])}` : `${t('f.to')} ${format(v[1] as number)}`);
  const list = (vals: string[], format: (v: string) => string) => (vals.length > 2 ? `${format(vals[0])} +${vals.length - 1}` : vals.map(format).join(', '));
  const value = (f as unknown as Record<string, unknown>)[k];
  const isRange = (RANGE_KEYS as readonly string[]).includes(k);
  const set = Array.isArray(value) && (isRange ? value.some(v => v != null) : value.length > 0);
  if (!set) return [t('f.' + k), false];
  if (k === 'price') return [range(f.price, compactMoney), true];
  if (k === 'year') return [range(f.year, v => String(Math.round(v))), true];
  if (k === 'beds') return [list([...f.beds].sort(), b => (b === '0' ? t('f.studio') : b === '4' ? '4+' : b)) + ' ' + t('f.beds.short'), true];
  if (k === 'deal') return [list(f.deal, v => t('deal.' + v)), true];
  if (k === 'gearbox') return [list(f.gearbox, v => t('gearbox.' + v)), true];
  if (k === 'body') return [list(f.body, v => t('body.' + v)), true];
  return [list(value as string[], v => (k === 'district' ? fmt.place(v) : v)), true];
}

interface Props { serviceId: string; items: Item[] }

export default function Catalog({ serviceId, items }: Props) {
  const { fmt, live } = useSite();
  const { t } = fmt;
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const desktop = useDesktop();
  const svc = serviceOf(serviceId);
  const isCar = svc.group === 'auto';
  const hasMap = useMemo(() => items.some(hasPoint), [items]);
  const tabs: ServiceId[] = serviceId === 'all' ? (Object.keys(SERVICES) as ServiceId[]).filter(s => live.includes(s) && SERVICES[s].group === 'realty') : GROUPS[svc.group].services;

  const f = useMemo(() => parseFilters(search), [search]);
  const view = search.get('view') || (hasMap && desktop ? 'map' : 'list');
  const rows = useMemo(() => items.map(toRow), [items]);
  const found = useMemo(() => sortItems(applyFilters(rows, f), f.sort), [rows, f]);

  // The URL is the state: filters change it in place (no server round trip).
  const urlFor = (next: Filters, v = view) => {
    const qp = filtersToParams(next);
    if (v !== (hasMap && desktop ? 'map' : 'list')) qp.set('view', v);
    return `${pathname}${qp.toString() ? '?' + qp : ''}`;
  };
  const commit = (next: Filters, { replace = true, view: v = view } = {}) => {
    const url = urlFor(next, v);
    if (location.pathname + location.search === url) return;
    if (!replace) saveEntry({ top: pageTop() });
    if (replace) history.replaceState(null, '', url); else history.pushState(null, '', url);
  };
  // Below the desktop split view the map is the main full-screen map, showing exactly what the filters found.
  const mainMapHref = () => { const q = filtersToParams(f); q.set('from', serviceId); return '/map?' + q; };
  const wantsMainMap = view === 'map' && !desktop;
  useEffect(() => { if (wantsMainMap) router.replace(mainMapHref()); });

  // Search box: typed text goes to the URL after a short pause.
  const [q, setQ] = useState(f.q);
  const [seenQ, setSeenQ] = useState(f.q);
  if (seenQ !== f.q) { setSeenQ(f.q); setQ(f.q); }
  const typing = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(typing.current), []);
  const onSearch = (value: string) => {
    setQ(value);
    clearTimeout(typing.current);
    typing.current = setTimeout(() => commit({ ...f, q: value }), 180);
  };

  // The list grows as it is scrolled.
  const [limit, setLimit] = useState(PAGE);
  const [seenFound, setSeenFound] = useState(found);
  if (seenFound !== found) { setSeenFound(found); setLimit(PAGE); }
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || limit >= found.length) return;
    const io = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) setLimit(n => n + PAGE); }, { root: scrollRoot(), rootMargin: '900px 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, [limit, found.length]);

  // For our own analytics: what was searched and whether anything was found.
  useEffect(() => { trackSearch(serviceId, filtersToParams({ ...f, sort: 'new' }).toString(), found.length); }, [serviceId, f, found.length]);

  const [sheet, setSheet] = useState<{ only: string; anchor: DOMRect | null } | null>(null);
  const [hot, setHot] = useState<string | null>(null);
  const chips = useMemo(() => activeChips(f, fmt), [f, fmt]);
  const n = activeCount(f);
  const pills = ['price', 'beds', 'deal', 'district', 'body', 'year', 'gearbox'].filter(k => svc.filters.includes(k)).slice(0, 3);
  const sortOptions = ['new', 'cheap', 'expensive', isCar ? 'year' : 'area', ...(items.some(x => x.ppsqm_usd) ? ['ppsqm'] : [])];
  const searchLabel = t(isCar ? 'cat.search.car' : 'cat.search');
  const missing = found.length - found.filter(hasPoint).length;

  // "Nothing found": offer to drop the single filter that brings back the most offers.
  const suggestions = () => {
    const options: { i: number | 'q'; label: string; n: number }[] = chips.map((c, i) => {
      const next = structuredClone(f);
      c.apply(next);
      return { i, label: c.label, n: applyFilters(rows, next).length };
    }).filter(o => o.n > 0).sort((a, b) => b.n - a.n).slice(0, 3);
    const withoutQ = f.q ? applyFilters(rows, { ...f, q: '' }).length : 0;
    if (withoutQ) options.unshift({ i: 'q', label: `«${f.q}»`, n: withoutQ });
    const drop = (i: number | 'q') => {
      if (i === 'q') return commit({ ...f, q: '' });
      const next = structuredClone(f);
      chips[i].apply(next);
      commit(next);
    };
    return (
      <div className="suggest">
        {options.map(o => <button key={o.i} type="button" className="chip" onClick={() => drop(o.i)}><Icon name="x" />{t('cat.drop', o.label, o.n)}</button>)}
        {(n > 0 || f.q) && <button type="button" className="btn btn-primary" onClick={clearAll}>{t('cat.reset')}</button>}
      </div>
    );
  };
  const clearAll = () => commit(parseFilters(new URLSearchParams(f.sort !== 'new' ? 'sort=' + f.sort : '')));
  const setView = (v: string) => { commit(f, { view: v }); if (v === 'list' && !desktop) setPageTop(0); };

  return (
    <section className="catalog" data-view={view}>
      <div className="container cat-top">
        <div className="cat-title"><h1>{t('svc.' + serviceId)}</h1><span className="cat-count" aria-live="polite">{t('cat.count', found.length)}</span></div>
        <div className="svc-tabs" role="tablist">
          {tabs.map(s => (
            <Link key={s} role="tab" className={`svc-tab${s === serviceId ? ' on' : ''}`} href={`/${s}`} aria-selected={s === serviceId} prefetch={false}>
              <Icon name={SERVICES[s].icon} />{t('svc.' + s + '.short')}{live.includes(s) ? '' : <sup>{t('svc.soon')}</sup>}
            </Link>
          ))}
        </div>
      </div>
      <div className="toolbar-wrap">
        <div className="container toolbar">
          <label className="search"><Icon name="search" /><input type="search" value={q} onChange={e => onSearch(e.target.value)} placeholder={searchLabel} aria-label={searchLabel} /></label>
          <div className="pills" role="group" aria-label={t('cat.filters')}>
            <button type="button" className={`pill filters-btn${n > 0 ? ' on' : ''}`} aria-label={t('cat.filters.all')} onClick={() => setSheet({ only: '', anchor: null })}>
              <Icon name="sliders" /><span>{t('cat.filters')}</span><b className="nbadge">{n || ''}</b>
            </button>
            {pills.map(k => {
              const [label, on] = pillLabel(k, f, fmt);
              return <button key={k} type="button" className={`pill${on ? ' on' : ''}`} data-pill={k} onClick={e => setSheet({ only: k, anchor: e.currentTarget.getBoundingClientRect() })}><span>{label}</span><Icon name="down" /></button>;
            })}
            <div className="select sort pill-select"><Icon name="down" /><select aria-label={t('cat.sort')} value={f.sort} onChange={e => commit({ ...f, sort: e.target.value })}>
              {sortOptions.map(s => <option key={s} value={s}>{t('cat.sort.' + s)}</option>)}
            </select></div>
          </div>
          <div className="view-toggle" role="group" hidden={!hasMap}>
            {(['list', 'map'] as const).map(v => (
              <button key={v} type="button" className={view === v ? 'on' : undefined} aria-label={t('cat.view.' + v)} onClick={() => setView(v)}><Icon name={v} /><span>{t('cat.view.' + v)}</span></button>
            ))}
          </div>
        </div>
      </div>
      <div className="container active-row" hidden={!chips.length}>
        {chips.map((c, i) => <button key={i} type="button" className="chip on removable" onClick={() => { const next = structuredClone(f); c.apply(next); commit(next); }}>{c.label}<Icon name="x" /></button>)}
        {chips.length > 0 && <button type="button" className="link-btn" onClick={clearAll}>{t('cat.reset')}</button>}
      </div>
      <div className="cat-body">
        <div className="results">
          <div className="grid">
            {found.length
              ? found.slice(0, limit).map((x, i) => <ListingCard key={x.id} item={x} eager={i < 2} onHover={view === 'map' ? setHot : undefined} />)
              : <Empty title={t('cat.empty.t')} text={t('cat.empty.d')}>{suggestions()}</Empty>}
          </div>
          <div className="sentinel" ref={sentinel} />
        </div>
        <div className="map-pane">
          {view === 'map' && desktop && <CatalogMap items={found} hotId={hot} />}
          <div className="map-note" hidden={missing <= 0}>{missing > 0 ? `${fmt.num(missing)} ${t('cat.no.coords')}` : ''}</div>
        </div>
      </div>
      {hasMap && (
        <button type="button" className="fab-view" onClick={() => { if (view !== 'map') router.push(mainMapHref()); else setView('list'); }}>
          {view === 'map' ? <><Icon name="list" /><span>{t('cat.view.list')}</span></> : <><Icon name="map" /><span>{t('cat.view.map')}</span></>}
        </button>
      )}
      {sheet && (
        <FilterSheet serviceId={serviceId} base={items} filters={f} only={sheet.only} anchor={sheet.anchor} picker={!sheet.only}
          onClose={() => setSheet(null)}
          onApply={(next, service) => {
            if (service === serviceId) return commit(next, { replace: false });
            const qs = filtersToParams(next).toString();
            router.push('/' + service + (qs ? '?' + qs : ''));
          }} />
      )}
    </section>
  );
}
