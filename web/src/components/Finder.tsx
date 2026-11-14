// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// The home search: direction tabs, free text, district, budget, bedrooms, and a live result count.
import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Icon } from './Icon';
import { useFmt } from './Providers';
import { applyFilters, parseFilters, type Row } from '@/lib/filters';
import { thumb } from '@/lib/photos';
import { SERVICES, type IconName } from '@/lib/config';
import type { ServiceId } from '@/lib/types';

export interface FinderTab {
  service: ServiceId;
  icon: IconName;
  rows: Row[]; // the direction's listings, reduced to what the search looks at
  districts: [string, number][];
  steps: number[]; // budget steps in USD
  period?: string;
  rooms: boolean;
  pets: boolean;
}
const BEDS = ['0', '1', '2', '3', '4'];
interface State { q: string; district: string; max: string; beds: string[]; flags: string[] }
const EMPTY: State = { q: '', district: '', max: '', beds: [], flags: [] };

export default function Finder({ tabs, total, photo }: { tabs: FinderTab[]; total: number; photo?: string }) {
  const fmt = useFmt();
  const { t } = fmt;
  const router = useRouter();
  const [service, setService] = useState(tabs[0]?.service);
  const [state, setState] = useState<State>(EMPTY);
  const tab = tabs.find(x => x.service === service) ?? tabs[0];

  // Current choices as catalogue URL params; the same params drive the live count.
  const params = useMemo(() => {
    const q = new URLSearchParams();
    if (state.q.trim()) q.set('q', state.q.trim());
    if (state.district) q.set('district', state.district);
    if (state.max) q.set('price', '-' + state.max);
    if (state.beds.length) q.set('beds', state.beds.join(','));
    state.flags.forEach(k => q.set(k, '1'));
    return q;
  }, [state]);
  const count = useMemo(() => (tab ? applyFilters(tab.rows, parseFilters(params)).length : 0), [tab, params]);
  if (!tab) return null;
  const isCar = SERVICES[tab.service].group === 'auto';
  const set = (patch: Partial<State>) => setState(s => ({ ...s, ...patch }));
  const toggle = (key: 'beds' | 'flags', v: string) => setState(s => ({ ...s, [key]: s[key].includes(v) ? s[key].filter(x => x !== v) : [...s[key], v] }));
  const search = t(isCar ? 'cat.search.car' : 'cat.search');
  const per = tab.period ? ' ' + t('period.' + tab.period) : '';

  return (
    <form className="finder v-light" id="finder" noValidate style={{ '--fd-photo': `url('${photo ? thumb(photo) : ''}')` } as React.CSSProperties}
      onSubmit={e => { e.preventDefault(); const q = params.toString(); router.push(`/${tab.service}${q ? '?' + q : ''}`); }}>
      <div className="fd-head">
        <h2>{t('home.finder.title')}</h2>
        <p className="fd-facts"><span className="live-dot" /><b>{fmt.num(total)}</b> {t('home.stat.live')}<i />{t('home.finder.hourly')}</p>
      </div>
      <div className="fd-tabs" role="tablist">
        {tabs.map(x => (
          <button key={x.service} type="button" role="tab" data-svc={x.service} aria-selected={x.service === tab.service}
            onClick={() => { setService(x.service); setState(EMPTY); }}>
            <Icon name={x.icon} /><span>{x.service === 'car-rent' ? t('nav.auto') : t('svc.' + x.service + '.short')}</span>
          </button>
        ))}
      </div>
      <div className="fd-body" key={tab.service}>
        <label className="fd-search"><Icon name="search" /><input name="q" type="search" autoComplete="off" placeholder={search} aria-label={search} value={state.q} onChange={e => set({ q: e.target.value })} /></label>
        <div className="fd-row">
          {tab.districts.length > 0 && (
            <label className="fd-field"><span>{t('home.where')}</span><span className="fd-sel">
              <select name="district" value={state.district} onChange={e => set({ district: e.target.value })}>
                <option value="">{t('home.where.any')}</option>
                {tab.districts.map(([d, n]) => <option key={d} value={d}>{fmt.place(d)} · {n}</option>)}
              </select><Icon name="down" /></span></label>
          )}
          {tab.steps.length > 0 && (
            <label className="fd-field"><span>{t('home.budget')}</span><span className="fd-sel">
              <select name="max" value={state.max} onChange={e => set({ max: e.target.value })}>
                <option value="">{t('home.budget.any')}</option>
                {tab.steps.map(v => <option key={v} value={v}>{fmt.compactMoney(v)}{per}</option>)}
              </select><Icon name="down" /></span></label>
          )}
          {tab.rooms && (
            <div className="fd-field fd-beds" role="group" aria-label={t('f.beds')}><span>{t('f.beds')}</span><div className="fd-seg">
              {BEDS.map(b => <button key={b} type="button" data-bed={b} aria-pressed={state.beds.includes(b)} onClick={() => toggle('beds', b)}>{b === '0' ? t('f.studio') : b === '4' ? '4+' : b}</button>)}
            </div></div>
          )}
        </div>
        {tab.pets && (
          <div className="fd-chips">
            <button type="button" className="fd-chip" data-flag="pets" aria-pressed={state.flags.includes('pets')} onClick={() => toggle('flags', 'pets')}><Icon name="heart" />{t('f.pets')}</button>
          </div>
        )}
        <button className={`btn fd-go${count ? '' : ' empty'}`} type="submit"><Icon name="search" /><span className="fd-go-label">{count ? t('home.finder.show', t('cat.count', count)) : t('home.finder.none')}</span><Icon name="arrow" /></button>
      </div>
    </form>
  );
}
