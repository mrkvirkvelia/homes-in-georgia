// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// All filters: bottom sheet on phones, side panel on desktop. One filter (`only`): a small popover under its pill
// button on desktop, a short bottom sheet on phones. The draft is applied (and written to the URL) on "Show".
import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './Icon';
import { useSite } from './Providers';
import { useFeed } from '@/lib/feed-client';
import { useLockBody } from '@/lib/hooks';
import type { Fmt } from '@/lib/format';
import { SERVICES, SERVICE_IDS, FILTER_AMENITIES, serviceOf, type IconName } from '@/lib/config';
import {
  FLAG_KEYS, LIST_KEYS, RANGE_KEYS, TEXT_KEYS, applyFilters, countBy, depositOf, itemsFor, toRow,
  type Filters, type Range,
} from '@/lib/filters';
import type { Item, ServiceId } from '@/lib/types';

type ListKey = (typeof LIST_KEYS)[number];
type RangeKey = (typeof RANGE_KEYS)[number];
type FlagKey = (typeof FLAG_KEYS)[number];
type TextKey = (typeof TEXT_KEYS)[number];

// Shown first in the sheet; everything else goes under "Advanced filter".
const BASIC_KEYS = new Set(['price', 'beds', 'kind', 'deal', 'district', 'body', 'gearbox']);
const BINS = 36;
const RES = 1000;

/** Square-root scale: fine control at the cheap end where most listings are. */
function scale(min: number, max: number) {
  const span = Math.max(1, max - min);
  return {
    toValue: (p: number) => min + span * (p / RES) ** 2,
    toPos: (v: number) => Math.round(Math.sqrt(Math.min(1, Math.max(0, (v - min) / span))) * RES),
  };
}
function niceStep(v: number) {
  if (v < 200) return 5;
  if (v < 2000) return 50;
  if (v < 20000) return 500;
  if (v < 200000) return 5000;
  return 10000;
}
const round = (v: number) => Math.round(v / niceStep(v)) * niceStep(v);
const percentile = (sorted: number[], q: number) => (sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(q * (sorted.length - 1)))] : 0);

// ---------- what the sheet shows ----------
interface RangeSection { kind: 'range'; id: string; key: RangeKey; title: string; money: boolean; plain: boolean; unit: string; min: number; max: number; bins: number[]; peak: number }
interface ChipSection { kind: 'chips'; id: string; key: ListKey | 'seats' | 'tenants' | 'term'; title: string; options: [string, string, number?][]; multi: boolean; limit: number }
interface ToggleSection { kind: 'toggles'; id: string; title: string; rows: [FlagKey, string][] }
interface SelectSection { kind: 'select'; id: string; key: 'pickup' | 'metro'; title: string; options: [string, number][]; any: string }
type Section = RangeSection | ChipSection | ToggleSection | SelectSection;

const present = (items: Item[], key: keyof Item) => new Set(items.map(x => x[key]).filter(Boolean) as (string | number)[]);

function range(id: RangeKey, values: (number | undefined)[], title: string, o: { money?: boolean; plain?: boolean; unit?: string } = {}): RangeSection | null {
  const sorted = values.filter((v): v is number => !!v && v > 0).sort((a, b) => a - b);
  if (sorted.length < 3) return null;
  const min = Math.floor(sorted[0]);
  const max = Math.ceil(percentile(sorted, 0.97));
  const sc = scale(min, max);
  const bins = new Array<number>(BINS).fill(0);
  sorted.forEach(v => { bins[Math.min(BINS - 1, Math.floor((sc.toPos(Math.min(v, max)) / RES) * BINS))]++; });
  return { kind: 'range', id, key: id, title, money: !!o.money, plain: !!o.plain, unit: o.unit ?? 'm²', min, max, bins, peak: Math.max(...bins) };
}

function buildSections(fmt: Fmt, serviceId: string, base: Item[]): Section[] {
  const { t } = fmt;
  const want = new Set(serviceOf(serviceId).filters);
  const out: (Section | null)[] = [];
  const period = base.find(x => x.period)?.period;
  const chips = (id: string, key: ChipSection['key'], title: string, options: ChipSection['options'], o: { multi?: boolean; limit?: number } = {}): ChipSection | null =>
    (options.length ? { kind: 'chips', id, key, title, options, multi: o.multi ?? true, limit: o.limit ?? 0 } : null);
  const known = (key: keyof Item, order: string[], label: (k: string) => string): ChipSection['options'] => {
    const have = present(base, key);
    return order.filter(k => have.has(k)).map(k => [k, label(k)]);
  };
  if (want.has('price')) out.push(range('price', base.map(x => x.price_usd), period ? `${t('f.price')} ${t('period.' + period)}` : t('f.price'), { money: true }));
  if (want.has('beds')) out.push(chips('beds', 'beds', t('f.beds'), [['0', t('f.studio')], ['1', '1'], ['2', '2'], ['3', '3'], ['4', '4+']]));
  if (want.has('kind')) out.push(chips('kind', 'kind', t('f.kind'), known('kind', ['apartment', 'house', 'commercial', 'land'], k => t('kind.' + k))));
  if (want.has('deal')) out.push(chips('deal', 'deal', t('f.deal'), known('deal', ['rent', 'sale'], k => t('deal.' + k))));
  if (want.has('area')) out.push(range('area', base.map(x => x.area), t('f.area')));
  if (want.has('year')) out.push(range('year', base.map(x => x.year), t('f.year'), { plain: true, unit: '' }));
  if (want.has('mileage')) out.push(range('mileage', base.map(x => x.mileage), t('f.mileage'), { unit: 'km' }));
  if (want.has('body')) out.push(chips('body', 'body', t('f.body'), known('body', ['suv', 'sedan', 'hatchback', 'minivan', 'wagon', 'coupe', 'pickup', 'business'], k => t('body.' + k))));
  if (want.has('gearbox')) out.push(chips('gearbox', 'gearbox', t('f.gearbox'), known('gearbox', ['auto', 'manual'], k => t('gearbox.' + k))));
  if (want.has('fuel')) out.push(chips('fuel', 'fuel', t('f.fuel'), known('fuel', ['petrol', 'diesel', 'hybrid', 'electric', 'gas'], k => t('fuel.' + k))));
  if (want.has('district')) out.push(chips('district', 'district', t('f.district'), countBy(base, 'district').map(([v, n]) => [v, fmt.place(v), n]), { limit: 10 }));
  if (want.has('seats')) {
    const seats = [...present(base, 'seats')].map(Number).sort((a, b) => a - b);
    out.push(chips('seats', 'seats', t('f.seats'), seats.map(v => [String(v), String(v)]), { multi: false }));
  }
  const select = (key: 'pickup' | 'metro', title: string, any: string): SelectSection | null => {
    const options = countBy(base, key);
    return options.length ? { kind: 'select', id: key, key, title, options, any } : null;
  };
  if (want.has('pickup')) out.push(select('pickup', t('f.pickup'), t('f.pickup.any')));
  if (want.has('metro')) out.push(select('metro', t('f.metro'), t('f.metro.any')));
  if (want.has('floor')) {
    out.push(range('floor', base.map(x => x.floor), t('f.floor'), { plain: true, unit: '' }));
    if (base.some(x => x.floor)) out.push({ kind: 'toggles', id: 'floorflags', title: t('f.floor.flags'), rows: [['notfirst', t('f.notfirst')], ['notlast', t('f.notlast')]] });
  }
  if (want.has('floors')) out.push(range('floors', base.map(x => x.floors), t('f.floors'), { plain: true, unit: '' }));
  if (want.has('building')) out.push(chips('building', 'building', t('f.building'), known('building', ['new', 'old', 'historical'], k => t('building.' + k))));
  if (want.has('condition')) out.push(chips('condition', 'condition', t('f.condition'), known('condition', ['renovated', 'mixed', 'white_frame', 'black_frame', 'green_frame', 'under_construction', 'old'], k => t('cond.' + k))));
  if (want.has('heating')) out.push(chips('heating', 'heating', t('l.heating'), known('heating', ['central', 'gas', 'electric'], k => t('heat.' + k))));
  if (want.has('amenities')) out.push(chips('amen', 'amen', t('f.amenities'), FILTER_AMENITIES.map(k => [k, t('am.' + k)])));
  if (want.has('ppsqm')) out.push(range('ppsqm', base.map(x => x.ppsqm_usd), t('f.ppsqm'), { money: true }));
  if (want.has('deposit')) out.push(range('deposit', base.map(x => depositOf(x) ?? 0), t('f.deposit'), { money: true }));
  if (want.has('tenants') && base.some(x => x.tenants)) out.push(chips('tenants', 'tenants', t('f.tenants'), [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4'], ['5', '5+']], { multi: false }));
  if (want.has('term')) out.push(chips('term', 'term', t('f.term'), [['short', t('term.short')], ['year', t('term.year')], ['long', t('term.long')]], { multi: false }));
  const flags: [FlagKey, string][] = [];
  if (want.has('pets')) flags.push(['pets', t('f.pets')]);
  if (want.has('flags')) flags.push(['excl', t('f.exclusive')]);
  if (flags.length) out.push({ kind: 'toggles', id: 'flags', title: t('f.flags'), rows: flags });
  return out.filter((s): s is Section => !!s);
}

export function clearFilter(f: Filters, key: string) {
  if ((LIST_KEYS as readonly string[]).includes(key)) f[key as ListKey] = [];
  else if ((RANGE_KEYS as readonly string[]).includes(key)) f[key as RangeKey] = [null, null];
  else if (key === 'flags') f.pets = f.excl = false;
  else if (key === 'floorflags') f.notfirst = f.notlast = false;
  else f[key as TextKey] = '';
}
/** Stay open when something inside the advanced part is already chosen, so an active filter is never hidden. */
function hasAdvanced(sections: Section[], f: Filters): boolean {
  const empty = (k: string) => { const v = (f as unknown as Record<string, unknown>)[k]; return !v || (Array.isArray(v) && !v.some(x => x != null && x !== '')); };
  return sections.filter(s => !BASIC_KEYS.has(s.id)).some(s => (s.id === 'flags' ? f.pets || f.excl : s.id === 'floorflags' ? f.notfirst || f.notlast : !empty(s.id)));
}
function clearAll(f: Filters) {
  LIST_KEYS.forEach(k => { f[k] = []; });
  RANGE_KEYS.forEach(k => { f[k] = [null, null]; });
  TEXT_KEYS.forEach(k => { f[k] = ''; });
  FLAG_KEYS.forEach(k => { f[k] = false; });
}

// ---------- controls ----------
/** Dual-handle range with a live histogram. Two native range inputs keep keyboard and screen-reader support. */
function RangeControl({ s, value, onChange, fmt }: { s: RangeSection; value: Range; onChange: (r: Range) => void; fmt: Fmt }) {
  const { t } = fmt;
  const sc = useMemo(() => scale(s.min, s.max), [s.min, s.max]);
  const display = (v: number) => (s.money ? Math.round(fmt.fromUsd(v)) : Math.round(v));
  const label = (v: number) => (s.money ? fmt.compactMoney(v) : s.plain ? String(Math.round(v)) : fmt.num(v) + ' ' + s.unit);
  const unit = s.money ? fmt.symbol : s.unit;
  const [va, vb] = value;
  // Raw slider positions and typed text are the control's own while it is used; they follow the draft only when it is reset (remount).
  const [pos, setPos] = useState<[number, number]>([va == null ? 0 : sc.toPos(va), vb == null ? RES : sc.toPos(vb)]);
  const [text, setText] = useState<[string, string]>([va == null ? '' : String(display(va)), vb == null ? '' : String(display(vb))]);
  const snap = s.plain ? Math.round : round;

  const fromSlider = (which: 0 | 1, raw: number) => {
    let [a, b] = pos;
    if (which === 0) a = Math.min(raw, b - 10); else b = Math.max(raw, a + 10);
    setPos([a, b]);
    const next: Range = [a <= 0 ? null : snap(sc.toValue(a)), b >= RES ? null : snap(sc.toValue(b))];
    setText([next[0] == null ? '' : String(display(next[0])), next[1] == null ? '' : String(display(next[1]))]);
    onChange(next);
  };
  const fromNumber = () => {
    const parse = (v: string) => (v === '' ? null : s.money ? fmt.toUsd(+v) : +v);
    const next: Range = [parse(text[0]), parse(text[1])];
    setPos([next[0] == null ? 0 : sc.toPos(next[0]), next[1] == null ? RES : sc.toPos(next[1])]);
    onChange(next);
  };
  const numberInput = (which: 0 | 1, placeholder: string, caption: string) => (
    <label><span>{caption}, {unit}</span>
      <input type="number" inputMode="numeric" min={0} placeholder={placeholder} value={text[which]}
        onChange={e => setText(x => (which ? [x[0], e.target.value] : [e.target.value, x[1]]))}
        onBlur={fromNumber} onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }} /></label>
  );

  return (
    <section className="f-section" data-key={s.id}>
      <div className="f-head"><h3>{s.title}</h3>
        <output className="f-out">{va == null && vb == null ? '' : `${va == null ? label(s.min) : label(va)} — ${vb == null ? label(s.max) + '+' : label(vb)}`}</output></div>
      <div className="range">
        <div className="hist">{s.bins.map((b, i) => <i key={i} className={(i + 0.5) / BINS * RES >= pos[0] && (i + 0.5) / BINS * RES <= pos[1] ? 'in' : undefined} style={{ height: `${Math.max(4, (b / s.peak) * 100)}%` }} />)}</div>
        <div className="range-track"><div className="range-fill" style={{ left: `${pos[0] / RES * 100}%`, right: `${100 - pos[1] / RES * 100}%` }} /></div>
        <input type="range" min={0} max={RES} step={1} value={pos[0]} aria-label={`${s.title} — ${t('f.from')}`} onChange={e => fromSlider(0, +e.target.value)} />
        <input type="range" min={0} max={RES} step={1} value={pos[1]} aria-label={`${s.title} — ${t('f.to')}`} onChange={e => fromSlider(1, +e.target.value)} />
      </div>
      <div className="range-inputs">
        {numberInput(0, String(display(s.min)), t('f.from'))}
        <i />
        {numberInput(1, `${display(s.max)}+`, t('f.to'))}
      </div>
    </section>
  );
}

function ChipsControl({ s, draft, onPatch, counts, fmt }: { s: ChipSection; draft: Filters; onPatch: (p: Partial<Filters>) => void; counts?: Map<string, number>; fmt: Fmt }) {
  const { t } = fmt;
  const [collapsed, setCollapsed] = useState(true);
  const isOn = (v: string) => (s.multi ? draft[s.key as ListKey].includes(v) : draft[s.key as TextKey] === v);
  const pick = (v: string) => {
    if (s.multi) { const l = draft[s.key as ListKey]; onPatch({ [s.key]: l.includes(v) ? l.filter(x => x !== v) : [...l, v] }); }
    else onPatch({ [s.key]: draft[s.key as TextKey] === v ? '' : v });
  };
  return (
    <section className="f-section" data-key={s.id}>
      <div className="f-head"><h3>{s.title}</h3></div>
      <div className={`chips${s.limit && collapsed ? ' collapsed' : ''}`}>
        {s.options.map(([value, text, total], i) => {
          const on = isOn(value);
          const n = counts ? counts.get(value) || 0 : total;
          return (
            <button key={value} type="button" className={`chip${s.limit && i >= s.limit ? ' extra' : ''}${on ? ' on' : ''}${counts && !n && !on ? ' dim' : ''}`} aria-pressed={on} onClick={() => pick(value)}>
              {text}{n != null && <> <small>{n}</small></>}
            </button>
          );
        })}
      </div>
      {s.limit > 0 && s.options.length > s.limit && (
        <button type="button" className={`more-btn${collapsed ? '' : ' up'}`} onClick={() => setCollapsed(!collapsed)}>{t(collapsed ? 'f.more' : 'f.less')} <Icon name="down" /></button>
      )}
    </section>
  );
}

function ToggleControl({ s, draft, onPatch }: { s: ToggleSection; draft: Filters; onPatch: (p: Partial<Filters>) => void }) {
  return (
    <section className="f-section" data-key={s.id}>
      <div className="f-head"><h3>{s.title}</h3></div>
      {s.rows.map(([key, text]) => (
        <label key={key} className="switch"><span>{text}</span>
          <input type="checkbox" checked={draft[key]} onChange={e => onPatch({ [key]: e.target.checked })} /><i /></label>
      ))}
    </section>
  );
}

function SelectControl({ s, draft, onPatch, fmt }: { s: SelectSection; draft: Filters; onPatch: (p: Partial<Filters>) => void; fmt: Fmt }) {
  return (
    <section className="f-section" data-key={s.id}>
      <div className="f-head"><h3>{s.title}</h3></div>
      <div className="select"><select value={draft[s.key]} onChange={e => onPatch({ [s.key]: e.target.value })}>
        <option value="">{s.any}</option>
        {s.options.map(([v, n]) => <option key={v} value={v}>{s.key === 'metro' ? fmt.place(v) : v} ({n})</option>)}
      </select><Icon name="down" /></div>
    </section>
  );
}

// ---------- the sheet ----------
interface Props {
  serviceId: string;
  base: Item[];
  filters: Filters;
  only?: string; // one filter: its section id
  anchor?: DOMRect | null; // position of the pill, for the popover
  picker?: boolean; // offer the other sections (directions)
  onApply: (next: Filters, service: string) => void;
  onClose: () => void;
}

export default function FilterSheet({ serviceId, base, filters, only = '', anchor = null, picker = false, onApply, onClose }: Props) {
  const { fmt } = useSite();
  const { t } = fmt;
  const [draft, setDraft] = useState<Filters>(() => structuredClone(filters));
  const [current, setCurrent] = useState(serviceId);
  const [open, setOpen] = useState(false);
  const [resetKey, setResetKey] = useState(0); // remounts the controls after a reset
  const popover = !!(only && anchor) && typeof matchMedia === 'function' && matchMedia('(min-width: 760px)').matches;
  const closeBtn = useRef<HTMLButtonElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useLockBody(!popover);

  // Another section has its own prices and parameters, so its listings come from the whole feed (fetched on demand).
  const feed = useFeed(current !== serviceId);
  const items = useMemo(() => (current === serviceId ? base : feed ? itemsFor(feed.items, current) : []), [current, serviceId, base, feed]);
  const rows = useMemo(() => items.map(toRow), [items]);
  const sections = useMemo(() => buildSections(fmt, current, items), [fmt, current, items]);
  const shown = only ? sections.filter(s => s.id === only) : sections;
  const title = only ? shown[0]?.title || t('f.title') : t('f.title');

  const patch = (p: Partial<Filters>) => setDraft(d => ({ ...d, ...p }));
  const matches = useMemo(() => applyFilters(rows, draft).length, [rows, draft]);
  const districtCounts = useMemo(() => new Map(countBy(applyFilters(rows, draft, 'district'), 'district')), [rows, draft]);

  const close = () => { setOpen(false); timer.current = setTimeout(onClose, 220); };
  const closeRef = useRef(close);
  useEffect(() => { closeRef.current = close; });
  useEffect(() => {
    const raf = requestAnimationFrame(() => { setOpen(true); closeBtn.current?.focus({ preventScroll: true }); });
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); };
    document.addEventListener('keydown', onKey);
    return () => { cancelAnimationFrame(raf); clearTimeout(timer.current); document.removeEventListener('keydown', onKey); };
  }, []);

  const pickService = (s: string) => {
    if (s === current) return;
    const next = structuredClone(draft);
    clearAll(next);
    setDraft(next);
    setCurrent(s);
    setResetKey(k => k + 1);
  };
  const reset = () => {
    const next = structuredClone(draft);
    if (only) clearFilter(next, only); else clearAll(next);
    setDraft(next);
    setResetKey(k => k + 1);
  };
  const [advOpen, setAdvOpen] = useState(() => hasAdvanced(sections, draft));
  const [advFor, setAdvFor] = useState(sections);
  if (advFor !== sections) { setAdvFor(sections); setAdvOpen(hasAdvanced(sections, draft)); }

  const render = (s: Section) => {
    const k = `${s.id}-${resetKey}`;
    if (s.kind === 'range') return <RangeControl key={k} s={s} value={draft[s.key]} fmt={fmt} onChange={r => patch({ [s.key]: r })} />;
    if (s.kind === 'chips') return <ChipsControl key={k} s={s} draft={draft} onPatch={patch} fmt={fmt} counts={s.id === 'district' ? districtCounts : undefined} />;
    if (s.kind === 'toggles') return <ToggleControl key={k} s={s} draft={draft} onPatch={patch} />;
    return <SelectControl key={k} s={s} draft={draft} onPatch={patch} fmt={fmt} />;
  };
  const style = popover && anchor ? { top: Math.round(anchor.bottom + 8), left: Math.round(Math.min(anchor.left, window.innerWidth - 400)) } : undefined;
  const advanced = only ? [] : shown.filter(s => !BASIC_KEYS.has(s.id));
  const { live } = useSite();
  const services: ServiceId[] = SERVICE_IDS.filter(s => live.includes(s));

  return (
    <div className={`sheet-wrap${popover ? ' pop' : ''}${only ? ' single' : ''}${open ? ' open' : ''}`}>
      <div className="sheet-backdrop" onClick={close} />
      <aside className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" style={style}>
        <header className="sheet-head"><span className="grab" /><h2 id="sheet-title">{title}</h2>
          <button className="icon-btn" type="button" ref={closeBtn} onClick={close} aria-label={t('nav.close')}><Icon name="x" /></button></header>
        <div className="sheet-body">
          {!only && picker && (
            <section className="f-section f-services">
              <div className="f-head"><h3>{t('f.section')}</h3></div>
              <div className="chips">{services.map(s => (
                <button key={s} type="button" className={`chip${s === current ? ' on' : ''}`} aria-pressed={s === current} onClick={() => pickService(s)}>
                  <Icon name={SERVICES[s].icon as IconName} />{t('svc.' + s + '.short')}</button>
              ))}</div>
            </section>
          )}
          {only ? shown.map(render) : <>
            {shown.filter(s => BASIC_KEYS.has(s.id)).map(render)}
            {advanced.length > 0 && (
              <details className="f-adv" open={advOpen} onToggle={e => setAdvOpen(e.currentTarget.open)}>
                <summary>{t('f.adv')}<Icon name="down" /></summary>
                {advanced.map(render)}
              </details>
            )}
          </>}
        </div>
        <footer className="sheet-foot"><button type="button" className="btn btn-ghost" onClick={reset}>{t(only ? 'f.clear' : 'cat.reset')}</button>
          <button type="button" className="btn btn-primary" onClick={() => { onApply(draft, current); close(); }}>{t('f.show', matches)}</button></footer>
      </aside>
    </div>
  );
}
