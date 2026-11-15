// «Продажа» and «Авто»: hge.ge's own objects besides rent (backend api/offers.py, services/offers.py), a menu item each.
// The form is the rent objects' generator (address on the map, chips of the old post generator's tags); photos and video
// sort and open as on a rent object (MediaGrid + Lightbox). Two publications: the site (status) and Telegram (the post).
import { useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ExternalLink, Globe, Plus, RotateCcw, Send, Upload } from 'lucide-react';
import { api } from '../../api';
import { itemsOf, thumbUrl } from '../../api/client';
import type { Offer, OfferKind, OfferStatus, PostFields } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { AddressField } from '../../components/AddressField';
import { errText, useToast } from '../../components/toast';
import { Badge, Button, Card, DistrictSelect, Empty, ErrorBox, Field, Input, Lightbox, Loading, PageHead, Seg, Select, Switch, Tabs, Textarea } from '../../components/ui';
import { distLabel, money } from '../../lib/format';
import { pool, shrinkPhoto } from '../../lib/upload';
import { Chips, MediaGrid, POST_ONE, POST_MANY, SALE_AMENITIES, SALE_BEDROOM_CHIPS, SALE_TYPES, type Shot } from '../properties/PropertyDetail';

const SITE: Record<OfferStatus, [string, 'ok' | 'grey' | 'warn']> = { draft: ['не на сайте', 'grey'], published: ['на сайте', 'ok'], archived: ['архив', 'warn'] };
const CURRENCY = [{ value: 'USD', label: '$ USD' }, { value: 'GEL', label: '₾ GEL' }, { value: 'EUR', label: '€ EUR' }];
const SERVICE: Record<string, string> = { sale: 'Вторичка', new: 'Новостройка', commercial: 'Коммерция' };
const GEARBOX: Record<string, string> = { auto: 'Автомат', manual: 'Механика' };
const FUEL: Record<string, string> = { petrol: 'Бензин', diesel: 'Дизель', hybrid: 'Гибрид', electric: 'Электро', gas: 'Газ' };
const BODY: Record<string, string> = { sedan: 'Седан', suv: 'Внедорожник', hatchback: 'Хэтчбек', wagon: 'Универсал', coupe: 'Купе', minivan: 'Минивэн', business: 'Бизнес', pickup: 'Пикап', convertible: 'Кабриолет' };
const MAX_PHOTO = 9;
const META = {
  sale: { path: '/sale', label: 'Объекты сайта', title: 'Продажа', add: 'Новый объект', what: 'Адрес' },
  car: { path: '/cars', label: 'Объекты сайта', title: 'Авто', add: 'Новое авто', what: 'Модель' },
};
const TABS: { value: OfferStatus | 'all'; label: string }[] = [{ value: 'all', label: 'Все' }, { value: 'draft', label: 'Не на сайте' }, { value: 'published', label: 'На сайте' }, { value: 'archived', label: 'Архив' }];
const one = (k: string) => POST_ONE[k][1];
const pfOf = (o: Offer | Draft) => (o.post_fields || {}) as PostFields;
const siteUrl = (o: Offer) => `https://hge.ge/listing/${o.item_id}`;
const shots = (o: Offer): Shot[] => [...o.photos.map((k) => ({ id: k, kind: 'photo' as const, room: null, src: k })), ...(o.video ? [{ id: o.video, kind: 'video' as const, room: null, src: o.video }] : [])];

function what(kind: OfferKind, o: Offer | Draft): string {
  if (kind === 'car') return [o.deal === 'sale' ? 'Продажа' : 'Аренда', BODY[String(o.body)]].filter(Boolean).join(' · ');
  const t = pfOf(o).prop_type;
  return [SERVICE[String(o.service)], t && one('prop_type')[t]].filter(Boolean).join(' · ');
}
const priceOf = (o: Offer) => (o.price != null ? `${money(o.price, o.currency)}${o.deal === 'rent' ? ` / ${o.period === 'month' ? 'мес' : 'день'}` : ''}` : '—');

export function OffersPage({ kind }: { kind: OfferKind }) {
  const m = META[kind];
  const nav = useNavigate();
  const [tab, setTab] = useState<OfferStatus | 'all'>('all');
  const [q, setQ] = useState('');
  const [view, setView] = useState<{ o: Offer; i: number } | null>(null);
  const list = useQuery({ queryKey: ['offers', kind, tab, q], queryFn: () => api.offers.list(kind, { status: tab === 'all' ? undefined : tab, q: q || undefined }) });
  const rows = itemsOf(list.data);
  return (
    <div className="col gap-lg">
      <PageHead label={m.label} title={m.title} actions={<Button onClick={() => nav(`${m.path}/new`)}><Plus size={16} />{m.add}</Button>} />
      <Card>
        <div className="col gap">
          <Tabs value={tab} onChange={setTab} tabs={TABS} />
          <Input placeholder={kind === 'car' ? 'Поиск по модели' : 'Поиск по адресу'} value={q} onChange={(e) => setQ(e.target.value)} />
          {list.isLoading ? <Loading /> : list.error ? <ErrorBox error={list.error} /> : rows.length === 0 ? <Empty text="Пока пусто" /> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th /><th>{m.what}</th><th>Тип</th><th>Цена</th><th>Сайт</th><th>Telegram</th></tr></thead>
                <tbody>
                  {rows.map((o) => (
                    <tr key={o.id} style={{ cursor: 'pointer' }} onClick={() => nav(`${m.path}/${o.id}`)}>
                      <td style={{ width: 56 }}>{o.photos[0] ? (
                        <img src={thumbUrl(o.photos[0])} alt="" width={48} height={48} style={{ objectFit: 'cover', borderRadius: 6, cursor: 'zoom-in' }}
                          onClick={(e) => { e.stopPropagation(); setView({ o, i: 0 }); }} />) : null}</td>
                      <td><b>{o.title}</b>{o.district ? <small className="muted"> · {String(o.district)}</small> : null}</td>
                      <td>{what(kind, o)}</td>
                      <td>{priceOf(o)}</td>
                      <td>{o.public ? <a href={siteUrl(o)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><Badge tone="ok">на сайте</Badge></a> : <Badge tone={SITE[o.status][1]}>{SITE[o.status][0]}</Badge>}</td>
                      <td>{o.post_url ? <a href={o.post_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>пост <ExternalLink size={12} /></a> : <span className="faint">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
      {view && <Lightbox items={shots(view.o)} index={view.i} onIndex={(i) => setView({ ...view, i })} onClose={() => setView(null)} />}
    </div>
  );
}

type Draft = Record<string, unknown> & { post_fields?: PostFields };
const NEW: Record<OfferKind, Draft> = { sale: { service: 'sale', currency: 'USD', post_fields: { prop_type: 'Apartment' } }, car: { deal: 'rent', period: 'day', currency: 'USD' } };
const KEYS: Record<OfferKind, string[]> = {
  sale: ['service', 'title', 'district', 'lat', 'lng', 'price', 'currency', 'rooms', 'area', 'floor', 'floors', 'completion', 'post_fields', 'description', 'is_exclusive'],
  car: ['deal', 'title', 'period', 'deposit', 'year', 'gearbox', 'fuel', 'body', 'seats', 'mileage', 'pickup', 'lat', 'lng', 'price', 'currency', 'description', 'is_exclusive'],
};
const NUM = new Set(['price', 'deposit', 'rooms', 'area', 'floor', 'floors', 'year', 'seats', 'mileage']);

/** the form's values -> the request body (empty string = cleared field) */
function body(kind: OfferKind, d: Draft): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const k of KEYS[kind]) {
    const v = d[k];
    out[k] = k === 'is_exclusive' ? !!v : k === 'post_fields' ? (v || {}) : v === '' || v == null ? null : NUM.has(k) ? Number(v) : v;
  }
  if (kind === 'car' && d.deal === 'sale') Object.assign(out, { period: null, deposit: null });
  if (kind === 'car' && d.deal === 'rent') out.mileage = null;
  if (kind === 'sale' && d.service !== 'new') out.completion = null;
  return out;
}

const s = (v: unknown) => (v == null ? '' : String(v));

/** The sale form: the rent generator's blocks with the old generator's sale block (types, beds up to 6+, condition). */
function SaleForm({ d, set }: { d: Draft; set: (patch: Draft) => void }) {
  const pf = pfOf(d);
  const [metroM, setMetroM] = useState<number | null>(null);
  const setPf = (k: string, v: unknown) => set({ post_fields: { ...pf, [k]: v === '' ? undefined : v } });
  const toggle = (a: string) => { const cur = pf.amenities || []; setPf('amenities', cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a]); };
  const point = d.lat != null && d.lng != null ? { lat: Number(d.lat), lng: Number(d.lng) } : null;
  return (
    <>
      <div className="gen-block">
        <span className="gen-title">1 · Основное</span>
        <Seg value={s(d.service) || 'sale'} onChange={(v) => set({ service: v })} options={Object.entries(SERVICE).map(([value, label]) => ({ value, label }))} />
        <Switch checked={!!d.is_exclusive} onChange={(v) => set({ is_exclusive: v })} label="❗️ Exclusive listing" />
        <Field label="Заголовок (необязательно)" hint="В посте: 🌟 заголовок 🌟"><Input value={pf.headline || ''} placeholder="Например: Вид на старый город" onChange={(e) => setPf('headline', e.target.value)} /></Field>
        <div className="field"><span className="label">Адрес *</span>
          <AddressField value={s(d.title)} onChange={(v) => set({ title: v })} point={point} onPoint={(p) => set({ lat: p?.lat ?? null, lng: p?.lng ?? null })}
            onFacts={(r) => { setMetroM(r.metro_m); set({ district: r.district || d.district, post_fields: { ...pf, metro: r.metro || pf.metro } }); }} /></div>
        <Field label="Район"><DistrictSelect value={s(d.district)} onChange={(v) => set({ district: v })} /></Field>
        <Field label="🚇 Метро" hint={metroM != null && pf.metro ? `≈ ${distLabel(metroM)} от точки на карте` : undefined}>
          <Select value={pf.metro || ''} placeholder="—" onChange={(e) => { setMetroM(null); setPf('metro', e.target.value); }} options={Object.entries(one('metro')).map(([value, label]) => ({ value, label }))} /></Field>
      </div>
      <div className="gen-block">
        <span className="gen-title">2 · Объект</span>
        <Field label="Тип"><Chips options={Object.fromEntries(SALE_TYPES.map((t) => [t, one('prop_type')[t]]))} value={pf.prop_type} onChange={(v) => setPf('prop_type', v)} /></Field>
        <Field label="Спальни"><Chips options={SALE_BEDROOM_CHIPS} value={s(d.rooms)} onChange={(v) => set({ rooms: v ?? '' })} /></Field>
        <Field label="Здание"><Chips options={one('building')} value={pf.building} onChange={(v) => setPf('building', v)} /></Field>
        <Field label="Состояние"><Chips options={one('condition')} value={pf.condition} onChange={(v) => setPf('condition', v)} /></Field>
        <div className="form-grid">
          <Field label="Площадь (м²)"><Input type="number" inputMode="decimal" value={s(d.area)} onChange={(e) => set({ area: e.target.value })} /></Field>
          <Field label="Этаж / Всего">
            <div className="row gap-sm" style={{ flexWrap: 'nowrap' }}>
              <Input type="number" inputMode="numeric" aria-label="Этаж" value={s(d.floor)} onChange={(e) => set({ floor: e.target.value })} />
              <span className="muted">/</span>
              <Input type="number" inputMode="numeric" aria-label="Всего этажей" value={s(d.floors)} onChange={(e) => set({ floors: e.target.value })} />
            </div>
          </Field>
          {d.service === 'new' && <Field label="Сдача дома" hint="Например: Q4 2027"><Input value={s(d.completion)} onChange={(e) => set({ completion: e.target.value })} /></Field>}
        </div>
        <Field label="Дизайн"><Chips options={one('design')} value={pf.design} onChange={(v) => setPf('design', v)} /></Field>
        <Field label="Ванные комнаты" hint="Одна — не отмечать"><Chips options={one('bathrooms')} value={pf.bathrooms} onChange={(v) => setPf('bathrooms', v)} /></Field>
        <Field label="Отопление"><Chips options={one('heating')} value={pf.heating} onChange={(v) => setPf('heating', v)} /></Field>
        <Field label="Удобства">
          <div className="row row-wrap gap-sm">
            {SALE_AMENITIES.map((a) => {
              const on = (pf.amenities || []).includes(a);
              return <button key={a} type="button" className={`chip ${on ? 'active' : ''}`} aria-pressed={on} onClick={() => toggle(a)}>{on ? <CheckCircle2 size={14} /> : null}{POST_MANY.amenities[1][a]}</button>;
            })}
          </div>
        </Field>
      </div>
      <div className="gen-block">
        <span className="gen-title">3 · Цена</span>
        <div className="form-grid">
          <Field label="Цена" hint="Диапазон цены (#Price…) ставится в пост сам"><Input type="number" inputMode="numeric" value={s(d.price)} onChange={(e) => set({ price: e.target.value })} /></Field>
          <Field label="Валюта"><Select value={s(d.currency) || 'USD'} onChange={(e) => set({ currency: e.target.value })} options={CURRENCY} /></Field>
        </div>
      </div>
    </>
  );
}

function CarForm({ d, set }: { d: Draft; set: (patch: Draft) => void }) {
  const rent = d.deal !== 'sale';
  const point = d.lat != null && d.lng != null ? { lat: Number(d.lat), lng: Number(d.lng) } : null;
  return (
    <>
      <div className="gen-block">
        <span className="gen-title">1 · Основное</span>
        <Seg value={rent ? 'rent' : 'sale'} onChange={(v) => set({ deal: v })} options={[{ value: 'rent', label: '🔑 Аренда' }, { value: 'sale', label: '💼 Продажа' }]} />
        <Switch checked={!!d.is_exclusive} onChange={(v) => set({ is_exclusive: v })} label="❗️ Exclusive listing" />
        <div className="form-grid">
          <Field label="Марка и модель *" hint="Первое слово — хештег марки: #Toyota"><Input value={s(d.title)} placeholder="Toyota Camry" onChange={(e) => set({ title: e.target.value })} /></Field>
          <Field label="Год"><Input type="number" inputMode="numeric" value={s(d.year)} onChange={(e) => set({ year: e.target.value })} /></Field>
        </div>
      </div>
      <div className="gen-block">
        <span className="gen-title">2 · Авто</span>
        <Field label="Кузов"><Chips options={BODY} value={s(d.body) || undefined} onChange={(v) => set({ body: v ?? '' })} /></Field>
        <Field label="Коробка"><Chips options={GEARBOX} value={s(d.gearbox) || undefined} onChange={(v) => set({ gearbox: v ?? '' })} /></Field>
        <Field label="Топливо"><Chips options={FUEL} value={s(d.fuel) || undefined} onChange={(v) => set({ fuel: v ?? '' })} /></Field>
        <div className="form-grid">
          <Field label="Мест"><Input type="number" inputMode="numeric" value={s(d.seats)} onChange={(e) => set({ seats: e.target.value })} /></Field>
          {!rent && <Field label="Пробег, км"><Input type="number" inputMode="numeric" value={s(d.mileage)} onChange={(e) => set({ mileage: e.target.value })} /></Field>}
        </div>
      </div>
      <div className="gen-block">
        <span className="gen-title">3 · Цена</span>
        <div className="form-grid">
          <Field label="Цена"><Input type="number" inputMode="numeric" value={s(d.price)} onChange={(e) => set({ price: e.target.value })} /></Field>
          <Field label="Валюта"><Select value={s(d.currency) || 'USD'} onChange={(e) => set({ currency: e.target.value })} options={CURRENCY} /></Field>
          {rent && <Field label="Цена за"><Seg value={s(d.period) || 'day'} onChange={(v) => set({ period: v })} options={[{ value: 'day', label: 'день' }, { value: 'month', label: 'месяц' }]} /></Field>}
          {rent && <Field label="Залог"><Input type="number" inputMode="numeric" value={s(d.deposit)} onChange={(e) => set({ deposit: e.target.value })} /></Field>}
        </div>
      </div>
      <div className="gen-block">
        <span className="gen-title">4 · {rent ? 'Где забрать' : 'Где посмотреть'}</span>
        <AddressField value={s(d.pickup)} onChange={(v) => set({ pickup: v })} point={point} onPoint={(p) => set({ lat: p?.lat ?? null, lng: p?.lng ?? null })} />
      </div>
    </>
  );
}

/** Photos and video as on a rent object: up to 9 photos + 1 video, drag to sort, a tap opens the Lightbox. */
function Media({ kind, o, onChange }: { kind: OfferKind; o: Offer; onChange: (o: Offer) => void }) {
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<Record<number, number>>({});
  const run = (p: Promise<Offer>) => p.then(onChange, (e) => toast(errText(e), true));
  const pick = async (files: File[]) => {
    let ph = o.photos.length, vd = o.video ? 1 : 0;
    const isVideo = (f: File) => f.type.startsWith('video/');
    const fit = files.filter((f) => (isVideo(f) ? ++vd <= 1 : ++ph <= MAX_PHOTO));
    if (fit.length < files.length) toast(`Не добавлено ${files.length - fit.length}: максимум ${MAX_PHOTO} фото и 1 видео`, true);
    await pool(fit, 3, async (f, i) => {
      try {
        const small = await shrinkPhoto(f);
        onChange(await api.offers.upload(kind, o.id, small, (p) => setBusy((b) => ({ ...b, [i]: Math.round(p * 100) }))));
      } catch (e) { toast(errText(e), true); }
      setBusy((b) => { const { [i]: _, ...rest } = b; return rest; });
    });
  };
  const full = o.photos.length >= MAX_PHOTO && !!o.video;
  const pending = Object.values(busy);
  return (
    <Card label="Сайт и пост берут первое фото обложкой" title={`Фото ${o.photos.length}/${MAX_PHOTO} · Видео ${o.video ? 1 : 0}/1`}>
      <div className="col gap">
        <input ref={file} type="file" accept="image/*,video/*" multiple hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ''; if (f.length) pick(f); }} />
        <Button block loading={pending.length > 0} disabled={full} onClick={() => file.current?.click()}><Upload size={16} />{full ? 'Загружено максимум файлов' : 'Загрузить фото и видео'}</Button>
        {pending.length > 0 && <div className="muted" style={{ fontSize: 12 }}>Загружаем: {pending.map((p) => `${p}%`).join(' · ')}</div>}
        <MediaGrid items={shots(o)} grouped
          onOrder={(ids) => run(api.offers.order(kind, o.id, ids.map(String).filter((k) => k !== o.video)))}
          onDelete={(k) => { if (confirm('Удалить файл?')) run(api.offers.deleteFile(kind, o.id, String(k))); }} />
      </div>
    </Card>
  );
}

/** The two publications: the site hge.ge (status) and the Telegram post (operators, as for rent objects). */
function Publish({ kind, o, dirty, onChange }: { kind: OfferKind; o: Offer; dirty: boolean; onChange: (o: Offer) => void }) {
  const toast = useToast();
  const { isStaff } = useAuth();
  const post = useQuery({ queryKey: ['offer-post', kind, o.id, o.updated_at], queryFn: () => api.offers.post(kind, o.id) });
  const [edited, setEdited] = useState<string | null>(null);
  const text = edited ?? post.data?.text ?? '';
  const status = useMutation({
    mutationFn: (st: OfferStatus) => api.offers.setStatus(kind, o.id, st),
    onSuccess: (x) => { onChange(x); toast(x.status === 'published' ? 'Опубликовано на сайте' : x.status === 'draft' ? 'Снято с сайта' : 'В архиве'); },
    onError: (e) => toast(errText(e), true),
  });
  const tg = useMutation({
    mutationFn: () => api.offers.telegram(kind, o.id, edited ?? undefined),
    onSuccess: (x) => { onChange(x); toast(x.post_url ? 'Опубликовано в Telegram' : 'Пост собран (dev: без отправки)'); },
    onError: (e) => toast(errText(e), true),
  });
  const noPhoto = !o.photos.length;
  return (
    <Card title="Публикация">
      <div className="col gap-lg">
        {dirty && <div className="alert alert-warn">Есть несохранённые правки — сначала «Сохранить».</div>}
        {noPhoto && <div className="alert alert-warn">Чтобы опубликовать, добавьте хотя бы одно фото.</div>}
        <div className="gen-block">
          <div className="row row-between row-wrap gap-sm"><span className="gen-title">Сайт hge.ge</span><Badge tone={SITE[o.status][1]}>{SITE[o.status][0]}</Badge></div>
          <div className="row row-wrap gap-sm">
            {o.status !== 'published'
              ? <Button variant="ok" loading={status.isPending} disabled={dirty || noPhoto} onClick={() => status.mutate('published')}><Globe size={16} />Опубликовать на сайте</Button>
              : <>
                <a className="btn btn-secondary" href={siteUrl(o)} target="_blank" rel="noreferrer"><ExternalLink size={16} />Открыть на сайте</a>
                <Button variant="ghost" loading={status.isPending} onClick={() => status.mutate('draft')}>Снять с сайта</Button>
              </>}
            {o.status !== 'archived' && <Button variant="ghost" loading={status.isPending} onClick={() => { if (confirm('Убрать в архив? С сайта пропадёт.')) status.mutate('archived'); }}>В архив</Button>}
          </div>
        </div>
        <div className="gen-block">
          <div className="row row-between row-wrap gap-sm"><span className="gen-title">Telegram</span>{o.post_url ? <a href={o.post_url} target="_blank" rel="noreferrer">пост в канале <ExternalLink size={12} /></a> : <span className="faint" style={{ fontSize: 12 }}>ещё не опубликован</span>}</div>
          {post.isLoading ? <Loading /> : (
            <Field label="Текст поста" hint="Собран из полей выше, как в генераторе постов. 📍[адрес](ссылка) станет ссылкой на карту.">
              <Textarea value={text} rows={14} readOnly={!isStaff} onChange={(e) => setEdited(e.target.value)} style={{ fontFamily: 'inherit', lineHeight: 1.45 }} />
            </Field>
          )}
          {edited !== null && <Button size="sm" variant="ghost" onClick={() => setEdited(null)}><RotateCcw size={14} />Исходный текст</Button>}
          {isStaff
            ? <Button variant="ok" loading={tg.isPending} disabled={dirty || noPhoto || !text.trim()} onClick={() => { if (confirm(o.post_url ? 'Опубликовать ещё раз? Старый пост останется в канале.' : 'Опубликовать пост в Telegram?')) tg.mutate(); }}>
              <Send size={16} />{o.post_url ? 'Опубликовать в Telegram ещё раз' : 'Опубликовать в Telegram'}</Button>
            : <div className="muted" style={{ fontSize: 12 }}>В Telegram публикует оператор.</div>}
        </div>
      </div>
    </Card>
  );
}

export function OfferCardPage({ kind }: { kind: OfferKind }) {
  const m = META[kind];
  const { id } = useParams();
  const isNew = id === 'new';
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['offer', kind, id], queryFn: () => api.offers.get(kind, Number(id)), enabled: !isNew });
  const [draft, setDraft] = useState<Draft | null>(null);
  const o = q.data;
  const d: Draft = draft ?? (isNew ? NEW[kind] : (o as Draft) ?? {});
  const set = (patch: Draft) => setDraft((x) => ({ ...(x ?? d), ...patch }));
  const fresh = (x: Offer) => { qc.setQueryData(['offer', kind, String(x.id)], x); qc.invalidateQueries({ queryKey: ['offers', kind] }); };
  const save = useMutation({
    mutationFn: () => (isNew ? api.offers.create(kind, body(kind, d)) : api.offers.update(kind, Number(id), body(kind, d))),
    onSuccess: (x) => { setDraft(null); fresh(x); toast('Сохранено'); if (isNew) nav(`${m.path}/${x.id}`, { replace: true }); },
    onError: (e) => toast(errText(e), true),
  });
  if (!isNew && q.isLoading) return <Loading />;
  if (!isNew && !o) return <ErrorBox error={q.error ?? new Error('Не найдено')} />;
  const ready = !!s(d.title).trim();
  return (
    <div className="col gap-lg">
      <div><Link to={m.path} className="muted" style={{ fontSize: 13 }}>← {m.title}</Link></div>
      <PageHead label={[m.title, what(kind, d)].filter(Boolean).join(' · ')} title={isNew ? m.add : String(o!.title)}
        actions={o && <><Badge tone={SITE[o.status][1]}>{SITE[o.status][0]}</Badge>{o.post_url && <Badge tone="blue">в Telegram</Badge>}</>} />
      <Card>
        <div className="col gap-lg">
          {kind === 'sale' ? <SaleForm d={d} set={set} /> : <CarForm d={d} set={set} />}
          <Field label="Описание"><Textarea rows={5} value={s(d.description)} onChange={(e) => set({ description: e.target.value })} /></Field>
          <div className="row gap-sm row-wrap">
            <Button size="lg" loading={save.isPending} disabled={!ready || (!isNew && !draft)} onClick={() => save.mutate()}>Сохранить</Button>
            {!ready && <span className="faint" style={{ fontSize: 12, alignSelf: 'center' }}>Укажите {kind === 'car' ? 'модель' : 'адрес'}</span>}
          </div>
        </div>
      </Card>
      {isNew ? <Empty text="Фото, видео и публикация — после сохранения" /> : o && <>
        <Media kind={kind} o={o} onChange={fresh} />
        <Publish kind={kind} o={o} dirty={!!draft} onChange={fresh} />
      </>}
    </div>
  );
}
