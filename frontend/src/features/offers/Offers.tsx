// «Продажа» and «Авто»: the objects of the site hge.ge that are not rent (backend api/offers.py, services/offers.py).
// Agents add and edit them by hand; «Опубликовать» (a photo is needed) puts one on the site at once.
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, ExternalLink, ImagePlus, Plus, Trash2 } from 'lucide-react';
import { api } from '../../api';
import { itemsOf, mediaUrl, thumbUrl } from '../../api/client';
import type { Offer, OfferKind, OfferStatus } from '../../api/types';
import { errText, useToast } from '../../components/toast';
import { SubNav } from '../../layout/AppLayout';
import { Badge, Button, Card, DistrictSelect, Empty, ErrorBox, Field, Input, Loading, PageHead, Select, Switch, Tabs, Textarea } from '../../components/ui';
import { money } from '../../lib/format';
import { pool, shrinkPhoto } from '../../lib/upload';

type Opts = [string, string][];
interface Spec { key: string; label: string; type?: 'num' | 'select' | 'district' | 'area' | 'bool' | 'amenities'; options?: Opts; span2?: boolean; hint?: string }

const STATUS: Record<OfferStatus, string> = { draft: 'Черновик', published: 'На сайте', archived: 'Архив' };
const TONE = { draft: 'grey', published: 'ok', archived: 'warn' } as const;
const CURRENCY: Opts = [['USD', 'USD'], ['GEL', 'GEL'], ['EUR', 'EUR']];
const METRO = ['Liberty Square', 'Rustaveli', 'Marjanishvili', 'Station Square', 'Tsereteli', 'Gotsiridze', 'Nadzaladevi', 'Didube', 'Grmagele', 'Guramishvili', 'Sarajishvili',
  'Akhmeteli Theatre', 'Technical University', 'Vazha-Pshavela', 'Delisi', 'State University', 'Medical University', 'Avlabari', 'Isani', '300 Aragveli', 'Samgori', 'Varketili'];
const AMENITIES: Opts = [['balcony', 'Балкон'], ['terrace', 'Терраса'], ['courtyard', 'Двор'], ['parking', 'Парковка'], ['conditioner', 'Кондиционер'], ['elevator', 'Лифт'],
  ['wifi', 'Wi-Fi'], ['tv', 'ТВ'], ['dishwasher', 'Посудомойка'], ['stove', 'Плита'], ['oven', 'Духовка'], ['microwave', 'СВЧ'], ['washer', 'Стиралка'], ['vacuum', 'Пылесос'],
  ['fireplace', 'Камин'], ['bath', 'Ванна'], ['shower', 'Душ']];

// the form, field by field; keys are the backend columns
const FIELDS: Record<OfferKind, Spec[]> = {
  sale: [
    { key: 'service', label: 'Направление *', type: 'select', options: [['sale', 'Вторичка'], ['new', 'Новостройка'], ['commercial', 'Коммерция (продажа)']] },
    { key: 'kind', label: 'Тип', type: 'select', options: [['apartment', 'Квартира'], ['house', 'Дом'], ['land', 'Участок'], ['commercial', 'Коммерческое']] },
    { key: 'title', label: 'Адрес *', span2: true },
    { key: 'headline', label: 'Заголовок для сайта', span2: true },
    { key: 'district', label: 'Район', type: 'district' },
    { key: 'metro', label: 'Метро', type: 'select', options: METRO.map((m) => [m, m]) },
    { key: 'price', label: 'Цена', type: 'num' },
    { key: 'currency', label: 'Валюта', type: 'select', options: CURRENCY },
    { key: 'rooms', label: 'Спален', type: 'num' },
    { key: 'area', label: 'Площадь, м²', type: 'num' },
    { key: 'floor', label: 'Этаж', type: 'num' },
    { key: 'floors', label: 'Этажей в доме', type: 'num' },
    { key: 'building', label: 'Дом', type: 'select', options: [['new', 'Новый'], ['old', 'Старый'], ['historical', 'Исторический']] },
    { key: 'condition', label: 'Состояние', type: 'select', options: [['white_frame', 'Белый каркас'], ['green_frame', 'Зелёный каркас'], ['black_frame', 'Чёрный каркас'], ['renovated', 'С ремонтом'], ['mixed', 'Смешанное'], ['old', 'Старое']] },
    { key: 'heating', label: 'Отопление', type: 'select', options: [['central', 'Центральное'], ['gas', 'Газовое'], ['electric', 'Электрическое']] },
    { key: 'completion', label: 'Сдача (новостройка)', hint: 'Например: Q4 2027' },
    { key: 'lat', label: 'Широта', type: 'num' },
    { key: 'lng', label: 'Долгота', type: 'num' },
    { key: 'approx', label: 'Точка приблизительная (на сайте без точного пина)', type: 'bool', span2: true },
    { key: 'amenities', label: 'Удобства', type: 'amenities', span2: true },
    { key: 'description', label: 'Описание', type: 'area', span2: true },
    { key: 'is_exclusive', label: 'Эксклюзив', type: 'bool' },
    { key: 'post_url', label: 'Пост в Telegram', hint: 'Ссылка, если есть' },
  ],
  car: [
    { key: 'deal', label: 'Направление *', type: 'select', options: [['rent', 'Аренда'], ['sale', 'Продажа']] },
    { key: 'title', label: 'Модель *' },
    { key: 'price', label: 'Цена', type: 'num' },
    { key: 'currency', label: 'Валюта', type: 'select', options: CURRENCY },
    { key: 'period', label: 'Аренда: за', type: 'select', options: [['day', 'день'], ['month', 'месяц']] },
    { key: 'deposit', label: 'Залог', type: 'num' },
    { key: 'year', label: 'Год', type: 'num' },
    { key: 'gearbox', label: 'Коробка', type: 'select', options: [['auto', 'Автомат'], ['manual', 'Механика']] },
    { key: 'fuel', label: 'Топливо', type: 'select', options: [['petrol', 'Бензин'], ['diesel', 'Дизель'], ['hybrid', 'Гибрид'], ['electric', 'Электро']] },
    { key: 'body', label: 'Кузов', type: 'select', options: [['sedan', 'Седан'], ['suv', 'Внедорожник'], ['hatchback', 'Хэтчбек'], ['wagon', 'Универсал'], ['coupe', 'Купе'], ['minivan', 'Минивэн'], ['business', 'Бизнес']] },
    { key: 'seats', label: 'Мест', type: 'num' },
    { key: 'mileage', label: 'Пробег, км (продажа)', type: 'num' },
    { key: 'pickup', label: 'Где забрать (аренда)', span2: true },
    { key: 'lat', label: 'Широта', type: 'num' },
    { key: 'lng', label: 'Долгота', type: 'num' },
    { key: 'description', label: 'Описание', type: 'area', span2: true },
    { key: 'is_exclusive', label: 'Эксклюзив', type: 'bool' },
    { key: 'post_url', label: 'Пост в Telegram', hint: 'Ссылка, если есть' },
  ],
};
const NEW_DEFAULTS: Record<OfferKind, Record<string, unknown>> = { sale: { service: 'sale', kind: 'apartment', currency: 'USD' }, car: { deal: 'rent', period: 'day', currency: 'USD' } };
const META = {
  sale: { path: '/sale', label: 'Объекты сайта', title: 'Продажа', add: 'Новый объект', dir: (o: Offer) => ({ sale: 'Вторичка', new: 'Новостройка', commercial: 'Коммерция' }[String(o.service)] ?? '') },
  car: { path: '/cars', label: 'Объекты сайта', title: 'Авто', add: 'Новое авто', dir: (o: Offer) => (o.deal === 'sale' ? 'Продажа' : 'Аренда') },
};
const TABS: { value: OfferStatus | 'all'; label: string }[] = [{ value: 'all', label: 'Все' }, { value: 'draft', label: 'Черновики' }, { value: 'published', label: 'На сайте' }, { value: 'archived', label: 'Архив' }];
const siteUrl = (o: Offer) => `https://hge.ge/listing/${o.item_id}`;

function SiteLink({ o }: { o: Offer }) {
  return o.public ? <a href={siteUrl(o)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>на сайте <ExternalLink size={12} /></a> : null;
}

export function OffersPage({ kind }: { kind: OfferKind }) {
  const m = META[kind];
  const nav = useNavigate();
  const [tab, setTab] = useState<OfferStatus | 'all'>('all');
  const [q, setQ] = useState('');
  const list = useQuery({ queryKey: ['offers', kind, tab, q], queryFn: () => api.offers.list(kind, { status: tab === 'all' ? undefined : tab, q: q || undefined }) });
  const rows = itemsOf(list.data);
  return (
    <div className="col gap-lg">
      <SubNav items={[{ to: '/sale', label: 'Продажа' }, { to: '/cars', label: 'Авто' }]} />
      <PageHead label={m.label} title={m.title} actions={<Button onClick={() => nav(`${m.path}/new`)}><Plus size={16} />{m.add}</Button>} />
      <Card>
        <div className="col gap">
          <Tabs value={tab} onChange={setTab} tabs={TABS} />
          <Input placeholder="Поиск по названию / адресу" value={q} onChange={(e) => setQ(e.target.value)} />
          {list.isLoading ? <Loading /> : list.error ? <ErrorBox error={list.error} /> : rows.length === 0 ? <Empty text="Пока пусто" /> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th /><th>{kind === 'car' ? 'Модель' : 'Адрес'}</th><th>Направление</th><th>Цена</th><th>Статус</th><th /></tr></thead>
                <tbody>
                  {rows.map((o) => (
                    <tr key={o.id} style={{ cursor: 'pointer' }} onClick={() => nav(`${m.path}/${o.id}`)}>
                      <td style={{ width: 56 }}>{o.photos[0] ? <img src={thumbUrl(o.photos[0])} alt="" width={48} height={48} style={{ objectFit: 'cover', borderRadius: 6 }} /> : null}</td>
                      <td><b>{o.title}</b>{o.district ? <small className="muted"> · {String(o.district)}</small> : null}</td>
                      <td>{m.dir(o)}</td>
                      <td>{o.price != null ? `${money(o.price, o.currency)}${o.deal === 'rent' ? ` / ${o.period === 'month' ? 'мес' : 'день'}` : ''}` : '—'}</td>
                      <td><Badge tone={TONE[o.status]}>{STATUS[o.status]}</Badge></td>
                      <td><SiteLink o={o} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

type Draft = Record<string, unknown>;
const NUM = new Set(['price', 'deposit', 'rooms', 'area', 'floor', 'floors', 'year', 'seats', 'mileage', 'lat', 'lng']);

/** the form's values -> the request body (empty string = cleared field) */
function body(kind: OfferKind, d: Draft): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const s of FIELDS[kind]) {
    const v = d[s.key];
    if (s.type === 'bool') out[s.key] = !!v;
    else if (s.type === 'amenities') out[s.key] = Array.isArray(v) ? v : [];
    else if (NUM.has(s.key)) out[s.key] = v === '' || v == null ? null : Number(v);
    else out[s.key] = v === '' || v == null ? null : v;
  }
  if (kind === 'car' && d.deal === 'sale') out.period = null;
  return out;
}

function Photos({ kind, o, onChange }: { kind: OfferKind; o: Offer; onChange: (o: Offer) => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<Record<number, number>>({});
  const pick = async (files: File[]) => {
    const fit = files.slice(0, 9);
    await pool(fit, 3, async (f, i) => {
      try {
        const small = await shrinkPhoto(f);
        onChange(await api.offers.upload(kind, o.id, small, (p) => setBusy((b) => ({ ...b, [i]: Math.round(p * 100) }))));
      } catch (e) { toast(errText(e), true); }
      setBusy((b) => { const { [i]: _, ...rest } = b; return rest; });
    });
  };
  const run = (p: Promise<Offer>) => p.then(onChange, (e) => toast(errText(e), true));
  const move = (i: number, d: number) => {
    const k = [...o.photos];
    [k[i], k[i + d]] = [k[i + d], k[i]];
    run(api.offers.order(kind, o.id, k));
  };
  return (
    <Card label="Сайт показывает первое фото на обложке" title={`Фото ${o.photos.length}/9`}>
      <div className="col gap">
        <div className="photo-strip">
          {o.photos.map((k, i) => (
            <div key={k} className="ph">
              <img src={thumbUrl(k)} alt="" />
              <div className="row gap-sm" style={{ position: 'absolute', left: 4, bottom: 4 }}>
                <Button size="sm" variant="secondary" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Левее"><ArrowLeft size={12} /></Button>
                <Button size="sm" variant="secondary" disabled={i === o.photos.length - 1} onClick={() => move(i, 1)} aria-label="Правее"><ArrowRight size={12} /></Button>
              </div>
              <Button size="sm" variant="danger" className="del" onClick={() => { if (confirm('Удалить фото?')) run(api.offers.deleteFile(kind, o.id, k)); }} aria-label="Удалить"><Trash2 size={12} /></Button>
            </div>
          ))}
          {Object.entries(busy).map(([i, p]) => <div key={`b${i}`} className="ph" style={{ display: 'grid', placeItems: 'center' }}><span className="muted">{p}%</span></div>)}
        </div>
        {o.photos.length < 9 && (
          <label className="btn btn-secondary" style={{ alignSelf: 'start' }}>
            <ImagePlus size={16} />Добавить фото
            <input type="file" accept="image/*" multiple hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ''; pick(f); }} />
          </label>
        )}
        <div className="col gap-sm">
          <span className="label">Видео (одно)</span>
          {o.video ? (
            <div className="row gap-sm row-wrap">
              <a href={mediaUrl(o.video)} target="_blank" rel="noreferrer">Открыть видео</a>
              <Button size="sm" variant="ghost" onClick={() => { if (confirm('Удалить видео?')) run(api.offers.deleteFile(kind, o.id, o.video!)); }}><Trash2 size={14} />Удалить</Button>
            </div>
          ) : (
            <label className="btn btn-secondary btn-sm" style={{ alignSelf: 'start' }}>
              Добавить видео
              <input type="file" accept="video/*" hidden onChange={(e) => {
                const f = e.target.files?.[0]; e.target.value = '';
                if (f) run(api.offers.upload(kind, o.id, f, () => undefined));
              }} />
            </label>
          )}
        </div>
      </div>
    </Card>
  );
}

function Control({ s, d, set }: { s: Spec; d: Draft; set: (k: string, v: unknown) => void }) {
  const v = d[s.key];
  if (s.type === 'bool') return <div className={s.span2 ? 'span2' : ''} style={{ alignSelf: 'end' }}><Switch checked={!!v} onChange={(x) => set(s.key, x)} label={s.label} /></div>;
  if (s.type === 'amenities') {
    const cur = Array.isArray(v) ? (v as string[]) : [];
    return (
      <div className="span2 col gap-sm"><span className="label">{s.label}</span>
        <div className="row row-wrap gap">
          {AMENITIES.map(([k, l]) => (
            <label key={k} className="row gap-sm" style={{ cursor: 'pointer' }}>
              <input type="checkbox" checked={cur.includes(k)} onChange={(e) => set(s.key, e.target.checked ? [...cur, k] : cur.filter((x) => x !== k))} />{l}
            </label>
          ))}
          {cur.filter((k) => !AMENITIES.some((a) => a[0] === k)).map((k) => <Badge key={k} tone="grey">{k}</Badge>)}
        </div>
      </div>
    );
  }
  const str = v == null ? '' : String(v);
  const known = !s.options || !str || s.options.some((o) => o[0] === str);
  return (
    <Field label={s.label} hint={s.hint} className={s.span2 ? 'span2' : ''}>
      {s.type === 'select' ? <Select value={str} onChange={(e) => set(s.key, e.target.value)} placeholder="—"
        options={[...(known ? [] : [{ value: str, label: str }]), ...s.options!.map(([value, label]) => ({ value, label }))]} />
        : s.type === 'district' ? <DistrictSelect value={str} onChange={(x) => set(s.key, x)} />
        : s.type === 'area' ? <Textarea rows={6} value={str} onChange={(e) => set(s.key, e.target.value)} />
        : <Input type={s.type === 'num' ? 'number' : 'text'} step={s.type === 'num' ? 'any' : undefined} value={str} onChange={(e) => set(s.key, e.target.value)} />}
    </Field>
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
  const d: Draft = draft ?? (isNew ? NEW_DEFAULTS[kind] : o ?? {});
  const set = (k: string, v: unknown) => setDraft({ ...d, [k]: v });
  const fresh = (x: Offer) => { qc.setQueryData(['offer', kind, String(x.id)], x); qc.invalidateQueries({ queryKey: ['offers', kind] }); };
  const save = useMutation({
    mutationFn: () => (isNew ? api.offers.create(kind, body(kind, d)) : api.offers.update(kind, Number(id), body(kind, d))),
    onSuccess: (x) => { setDraft(null); fresh(x); toast('Сохранено'); if (isNew) nav(`${m.path}/${x.id}`, { replace: true }); },
    onError: (e) => toast(errText(e), true),
  });
  const status = useMutation({
    mutationFn: (s: OfferStatus) => api.offers.setStatus(kind, Number(id), s),
    onSuccess: (x) => { fresh(x); toast(x.status === 'published' ? 'Опубликовано на сайте' : x.status === 'draft' ? 'Снято с сайта' : 'В архиве'); },
    onError: (e) => toast(errText(e), true),
  });
  if (!isNew && q.isLoading) return <Loading />;
  if (!isNew && !o) return <ErrorBox error={q.error ?? new Error('Не найдено')} />;
  const ready = !!String(d.title ?? '').trim();
  return (
    <div className="col gap-lg">
      <div><Link to={m.path} className="muted" style={{ fontSize: 13 }}>← {m.title}</Link></div>
      <PageHead label={m.title} title={isNew ? m.add : String(o!.title)}
        actions={o && <><Badge tone={TONE[o.status]}>{STATUS[o.status]}</Badge><SiteLink o={o} /></>} />
      <Card title="Данные">
        <div className="form-grid">{FIELDS[kind].map((s) => <Control key={s.key} s={s} d={d} set={set} />)}</div>
        <div className="row gap-sm row-wrap mt">
          <Button loading={save.isPending} disabled={!ready || (!isNew && !draft)} onClick={() => save.mutate()}>Сохранить</Button>
          {o && o.status !== 'published' && <Button variant="ok" loading={status.isPending} disabled={!!draft || !o.photos.length} onClick={() => status.mutate('published')}>Опубликовать на сайте</Button>}
          {o && o.status === 'published' && <Button variant="secondary" loading={status.isPending} onClick={() => status.mutate('draft')}>Снять с сайта</Button>}
          {o && o.status !== 'archived' && <Button variant="ghost" loading={status.isPending} onClick={() => { if (confirm('Убрать в архив? С сайта пропадёт.')) status.mutate('archived'); }}>В архив</Button>}
        </div>
        {o && !o.photos.length && <p className="faint mt" style={{ fontSize: 12 }}>Чтобы опубликовать, добавьте хотя бы одно фото.</p>}
        {draft && !isNew && <p className="faint mt" style={{ fontSize: 12 }}>Есть несохранённые правки — сначала «Сохранить».</p>}
      </Card>
      {isNew ? <Empty text="Фото можно добавить после сохранения" /> : o && <Photos kind={kind} o={o} onChange={fresh} />}
    </div>
  );
}
