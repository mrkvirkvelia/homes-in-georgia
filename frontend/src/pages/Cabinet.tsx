import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, CalendarClock, CalendarDays, FileText } from 'lucide-react';
import { api } from '../api';
import { itemsOf } from '../api/client';
import type { PropertyStatus, User } from '../api/types';
import { FIELD_FILTER } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { PropertyStatusBadge } from '../components/domain';
import { errText, useToast } from '../components/toast';
import { Avatar, Badge, Button, Card, Drawer, Empty, ErrorBox, Field, Input, Loading, PageHead, Progress, Seg, Stat, Tabs } from '../components/ui';
import { ContractList } from '../features/contracts/ContractCard';
import { MyLeadsList } from '../features/leads/LeadBoard';
import { PropertyList } from '../features/properties/lists';
import { PROPERTY_STATUS, ROLE_LABEL, fmtDate, fmtSlot, money, monthLabel, phoneBlur, phoneFocus, phoneInput } from '../lib/format';
import { CalendarView } from './Calendar';
import { DealStatusBadge, DealView, DealsList } from './Deals';
import { LevelProgress } from './Team';
import { lx, t } from '../lib/i18n';

/** The avatar with «change photo» on click (Stanislav 11-16): admins for anyone, each employee for himself. */
export function AvatarEdit({ user, size }: { user: Pick<User, 'id' | 'name' | 'photo_url'>; size?: 'lg' }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { user: me, setMe } = useAuth();
  const [src, setSrc] = useState(user.photo_url);
  const up = useMutation({ mutationFn: (f: File) => api.users.photo(user.id, f),
    onSuccess: (u) => { setSrc(u.photo_url); if (me?.id === u.id) setMe?.({ ...me, photo_url: u.photo_url }); qc.invalidateQueries({ queryKey: ['users'] }); toast(t('Фото обновлено')); },
    onError: (e) => toast(errText(e), true) });
  if (!me || (me.id !== user.id && !['superadmin', 'admin'].includes(me.role))) return <Avatar size={size} name={user.name} src={src} />;
  return (
    <label title={t('Сменить фото')} style={{ cursor: 'pointer', position: 'relative', display: 'inline-flex', opacity: up.isPending ? 0.5 : 1 }}>
      <Avatar size={size} name={user.name} src={src} />
      <input type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) up.mutate(f); }} />
    </label>
  );
}

const CNT: [string, string][] = [['photo', t('Фото')], ['showing', t('Показы')], ['stickers', t('Расклейка')], ['rental', t('Сдачи')]];

export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
const MONTHS = lx(['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'],
  ['იანვარი', 'თებერვალი', 'მარტი', 'აპრილი', 'მაისი', 'ივნისი', 'ივლისი', 'აგვისტო', 'სექტემბერი', 'ოქტომბერი', 'ნოემბერი', 'დეკემბერი'],
  ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']);
/** «05-04» / «1990-05-04» → «4 мая» (day and month only: the year is private) */
export const birthdayLabel = (b?: string | null) => { const m = b?.match(/(\d\d)-(\d\d)$/); return m ? `${Number(m[2])} ${MONTHS[Number(m[1]) - 1]}` : ''; };

/** «Заполните профиль» (Irakli 11-12): the user fills his own missing name / birth date / phone / email. */
function ProfilePrompt({ u }: { u: User }) {
  const { setMe } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState({ first_name: u.first_name || '', last_name: u.last_name || '', birth_date: u.birth_date || '', phone: u.phone || '', email: u.email || '' });
  const save = useMutation({
    mutationFn: () => api.auth.updateMe({ first_name: f.first_name.trim(), last_name: f.last_name.trim(), birth_date: f.birth_date || null, phone: f.phone || null, email: f.email.trim() || null }),
    onSuccess: (me) => { setMe(me); qc.invalidateQueries({ queryKey: ['cabinet'] }); toast(t('Профиль сохранён')); },
    onError: (e) => toast(errText(e), true),
  });
  const ok = !!f.first_name.trim() && !!f.last_name.trim() && !!f.birth_date && f.phone.replace(/\D/g, '').length >= 9 && EMAIL_RE.test(f.email.trim());
  return (
    <Card label={t('Профиль')} title={t('Заполните профиль')}>
      <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>{t('Нужно агентству: чтобы связаться с вами и не пропустить ваш день рождения. Email видят только администраторы.')}</div>
      <div className="form-grid">
        <Field label={t('Имя')}><Input value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} placeholder={t('Заза')} autoComplete="given-name" /></Field>
        <Field label={t('Фамилия')}><Input value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} placeholder={t('Беридзе')} autoComplete="family-name" /></Field>
        <Field label={t('Дата рождения')}><Input type="date" value={f.birth_date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setF({ ...f, birth_date: e.target.value })} /></Field>
        <Field label={t('Телефон')}><Input type="tel" inputMode="tel" value={f.phone} onFocus={phoneFocus} onBlur={phoneBlur} onChange={(e) => { const v = phoneInput(e); setF((x) => ({ ...x, phone: v })); }} /></Field>
        <Field label={t('Email')}><Input type="email" inputMode="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} placeholder="name@mail.com" /></Field>
      </div>
      <div className="mt"><Button disabled={!ok} loading={save.isPending} onClick={() => save.mutate()}>{t('Сохранить')}</Button></div>
    </Card>
  );
}

/** userId: staff looking at an agent's cabinet (undefined = one's own); tabbed: the desktop «Обзор» tab, where
 * objects and deals have their own tabs (the Mini App keeps the short lists here). */
export function CabinetView({ base = '', userId, tabbed }: { base?: string; userId?: number; tabbed?: boolean }) {
  const { user } = useAuth();
  const { data, isLoading, error } = useQuery({ queryKey: ['cabinet', userId], queryFn: () => api.cabinet(userId) });
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;
  const u = data.user || user;
  const lvl = data.level;
  const leadLink = (id: number) => (base ? `${base}/leads/${id}` : `/leads/${id}`);
  const propLink = (id: number) => (base ? `${base}/properties/${id}` : `/objects/${id}`);
  const cur = data.monthly?.[0];
  const leases = data.expiring_leases || [];
  return (
    <div className="col gap-lg">
      <div className="card card-blue card-pad">
        <div className="row">
          {u ? <AvatarEdit key={u.id} user={u} size="lg" /> : <Avatar size="lg" />}
          <div className="grow">
            <div className="label">{u ? ROLE_LABEL[u.role] : ''}</div>
            <h2 style={{ color: '#fff', fontSize: 22, fontWeight: 900 }}>{u?.name}</h2>
            {u?.birthday && <div className="label" style={{ marginTop: 2 }}>🎂 {birthdayLabel(u.birthday)}</div>}
          </div>
          {lvl && <div style={{ textAlign: 'right' }}><div className="stat-value" style={{ marginTop: 0 }}>{lvl.level}%</div><div className="label">{t('уровень')}</div></div>}
        </div>
        {lvl && <div className="mt-lg"><LevelProgress deals={lvl.exclusive_deals} level={lvl.level} /><div className="label mt">{t('{n} эксклюзивных сделок', { n: lvl.exclusive_deals })}</div></div>}
      </div>

      {u && u.id === user?.id && !!u.profile_missing?.length && <ProfilePrompt u={u} />}

      {cur && (
        <div className="grid g4">
          <Stat label={t('Сделок · {m}', { m: monthLabel(cur.month) })} value={cur.deals} sub={t('аренда: {n}', { n: cur.rentals })} />
          <Stat label={t('Заработано за месяц')} value={money(cur.earned)} />
          <Stat label={t('Платформе за месяц')} value={money(cur.platform)} />
          <Stat label={t('Объектов добавлено')} value={cur.added} />
        </div>
      )}

      {data.counters && (
        <Card label={data.month ? monthLabel(data.month) : t('Этот месяц')} title={t('Мои счётчики')}>
          <div className="grid g4">
            {CNT.map(([k, label]) => {
              const c = data.counters?.[k as 'photo'];
              if (!c) return null;
              return (
                <div key={k} className="col gap-sm">
                  <div className="row row-between"><span className="label">{label}</span><b className="num">{c.done}/{c.plan}</b></div>
                  <Progress value={c.done} max={c.plan} />
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {(() => {
        const ch = (data as unknown as { channel_listings?: { active?: number; last_7_days?: number } }).channel_listings;
        const reps = ((data as unknown as { reports?: { id: number; kind: string; date?: string | null; created_at?: string }[] }).reports || []);
        return (
          <div className="grid g2">
            <Card label={t('Инструменты')} title={t('Быстрый доступ')}>
              <div className="add-grid">
                <Link to={`${base}/contracts?new=1`} className="add-item"><FileText size={20} /><span><b>{t('Договор')}</b><small>{t('Аренда или продажа')}</small></span></Link>
                <Link to={`${base}/calendar`} className="add-item"><CalendarDays size={20} /><span><b>{t('Календарь')}</b><small>{t('Показы и съёмки')}</small></span></Link>
                {!base && <Link to="/team?tab=standards" className="add-item"><BookOpen size={20} /><span><b>{t('Стандарты')}</b><small>{t('Лестница и викторина')}</small></span></Link>}
              </div>
            </Card>
            <Card label={t('Канал')} title={t('Мои публикации')}>
              {ch ? (
                <div className="grid g2">
                  <div><div className="label">{t('Активных')}</div><div className="stat-value">{ch.active ?? 0}</div></div>
                  <div><div className="label">{t('За 7 дней')}</div><div className="stat-value">{ch.last_7_days ?? 0}</div></div>
                </div>
              ) : <div className="muted">{t('Нет данных')}</div>}
              {reps.length > 0 && <div className="muted mt" style={{ fontSize: 12 }}>{t('Отчётов с моим участием: {n}, последний {d}', { n: reps.length, d: fmtDate(reps[0].date || reps[0].created_at) })}</div>}
            </Card>
          </div>
        );
      })()}

      <div className="grid g2">
        <Card label={t('Ближайшие')} title={t('Просмотры')}>
          {(data.viewings || []).length === 0 ? <Empty text={t('Просмотров не запланировано')} icon={<CalendarClock size={28} />} /> : (data.viewings || []).map((l) => (
            <Link key={l.id} to={leadLink(l.id)} className="list-row" style={{ color: 'inherit', textDecoration: 'none' }}>
              <Badge tone="solid">{l.viewing_at ? fmtSlot(l.viewing_at) : '—'}</Badge>
              <span className="grow ellipsis" style={{ fontWeight: 600 }}>{l.listing?.title}</span>
            </Link>
          ))}
        </Card>
        <Card label={t('Аренда')} title={t('Скоро заканчиваются')}>
          {(data.expiring || []).length === 0 && leases.length === 0 ? <Empty text={t('Нет договоров на продление')} /> : (data.expiring || []).map((d) => (
            <div key={d.id} className="list-row"><span className="grow"><b>{d.address}</b><div className="muted" style={{ fontSize: 12 }}>{t('до')} {fmtDate(d.rent_to)}</div></span><Badge tone="warn">{d.client_name}</Badge></div>
          ))}
          {/* objects with a lease end: ended in the last 2 weeks or ends within 2 months, time to re-rent */}
          {leases.map((p) => {
            const ended = new Date(p.rent_to) < new Date(new Date().toDateString());
            return (
              <Link key={`p${p.id}`} to={propLink(p.id)} className="list-row" style={{ color: 'inherit', textDecoration: 'none' }}>
                <span className="grow"><b>{p.address || t('Объект #{id}', { id: p.id })}</b><div className="muted" style={{ fontSize: 12 }}>{ended ? t('закончилась') : t('до')} {fmtDate(p.rent_to)}{p.tenant_name ? ` · ${p.tenant_name}` : ''}</div></span>
                <Badge tone={ended ? 'red' : 'warn'}>{ended ? t('пересдать') : t('аренда')}</Badge>
              </Link>
            );
          })}
        </Card>
      </div>

      {!tabbed && <div className="grid g2">
        <Card title={t('Мои объекты')}>
          {(data.properties || []).length === 0 ? <Empty text={t('Объектов нет')} /> : (data.properties || []).slice(0, 8).map((p) => (
            <Link key={p.id} to={propLink(p.id)} className="list-row" style={{ color: 'inherit', textDecoration: 'none' }}>
              <span className="grow ellipsis"><b>{p.address}</b> <span className="muted">{p.district}</span></span><PropertyStatusBadge status={p.status} />
            </Link>
          ))}
        </Card>
        <Card label={t('Сделки')} title={t('Мои сделки')}>
          {(data.deals || []).length === 0 ? <Empty text={t('Сделок нет')} /> : (data.deals || []).slice(0, 8).map((d) => (
            <div key={d.id} className="list-row">
              <span className="grow ellipsis"><b>{d.address || `#${d.id}`}</b><div className="muted" style={{ fontSize: 12 }}>{fmtDate(d.created_at)} · {t('моя доля')} {money(d.agent_amount)}</div></span>
              <DealStatusBadge s={d.status} />
            </div>
          ))}
        </Card>
      </div>}
      {!tabbed && !userId && <ContractList base={`${base}/contracts`} label={t('По сделкам')} title={t('Мои договоры')} />}
    </div>
  );
}

type Tab = 'overview' | 'objects' | 'deals' | 'contracts' | 'leads' | 'calendar' | 'stats';
const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: t('Обзор') }, { value: 'objects', label: t('Объекты') }, { value: 'deals', label: t('Сделки') }, { value: 'contracts', label: t('Договоры') },
  { value: 'leads', label: t('Заявки') }, { value: 'calendar', label: t('Календарь') }, { value: 'stats', label: t('Статистика') },
];
const DONE: PropertyStatus[] = ['published', 'rented', 'archived'];
const GROUPS: Record<string, { label: string; status: string }> = {
  work: { label: t('В работе'), status: (Object.keys(PROPERTY_STATUS) as PropertyStatus[]).filter((s) => !DONE.includes(s)).join(',') },
  published: { label: t('Опубликованные'), status: 'published' },
  rented: { label: t('Сданные'), status: 'rented' },
  archived: { label: t('Архив'), status: 'archived' },
};

function CabinetObjects({ agentId }: { agentId: number }) {
  const [g, setG] = useState('work');
  return (
    <div className="col">
      <Seg value={g} onChange={setG} options={Object.entries(GROUPS).map(([value, x]) => ({ value, label: x.label }))} />
      <PropertyList key={g} status={GROUPS[g].status} agentId={agentId} />
    </div>
  );
}

function CabinetDeals({ agentId }: { agentId: number }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      <DealsList agentId={agentId} onOpen={setOpen} />
      <Drawer open={!!open} onClose={() => setOpen(null)} title={t('Сделка #{id}', { id: open ?? '' })}>{open && <DealView id={open} onClose={() => setOpen(null)} />}</Drawer>
    </>
  );
}

/** per month: deals (rentals), objects added, the agent's money and the platform's share; bars scaled to the best month */
function CabinetStats({ userId }: { userId?: number }) {
  const { data, isLoading, error } = useQuery({ queryKey: ['cabinet', userId], queryFn: () => api.cabinet(userId) });
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;
  const rows = data.monthly || [];
  const max = Math.max(1, ...rows.map((r) => r.earned));
  const sum = (k: 'deals' | 'rentals' | 'added' | 'earned' | 'platform' | 'commission') => rows.reduce((a, r) => a + r[k], 0);
  return (
    <div className="col gap-lg">
      <div className="grid g4">
        <Stat label={t('Сделок за 12 месяцев')} value={sum('deals')} sub={t('аренда: {n}', { n: sum('rentals') })} />
        <Stat blue label={t('Заработано')} value={money(sum('earned'))} />
        <Stat label={t('Платформе')} value={money(sum('platform'))} sub={t('комиссия всего: {m}', { m: money(sum('commission')) })} />
        <Stat label={t('Объектов добавлено')} value={sum('added')} />
      </div>
      <div className="card table-wrap">
        <table className="table">
          <thead><tr><th>{t('Месяц')}</th><th>{t('Сделок')}</th><th>{t('Аренда')}</th><th>{t('Объектов')}</th><th>{t('Заработано')}</th><th className="hide-mobile">{t('Платформе')}</th><th className="hide-mobile">{t('Комиссия')}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.month}>
                <td className="nowrap">{monthLabel(r.month)}</td>
                <td className="num">{r.deals}</td>
                <td className="num">{r.rentals}</td>
                <td className="num">{r.added}</td>
                <td style={{ minWidth: 160 }}><div className="num" style={{ fontWeight: 700 }}>{money(r.earned)}</div><Progress value={r.earned} max={max} /></td>
                <td className="num hide-mobile">{money(r.platform)}</td>
                <td className="num hide-mobile">{money(r.commission)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="faint" style={{ fontSize: 12 }}>{t('Сделки без отменённых, по месяцу сделки. Заработано: доля агента плюс доля рекрутера, если он привёл. Платформе: доля платформы с его сделок.')}</div>
    </div>
  );
}

/** ?tab= one of TABS; staff open any agent's cabinet with ?user=<id>, agents always get their own */
export function CabinetPage() {
  const { user, isStaff } = useAuth();
  const [params, setParams] = useSearchParams();
  const set = (k: string, v: string) => { if (v) params.set(k, v); else params.delete(k); setParams(params, { replace: true }); };
  const tab = (params.get('tab') as Tab) || 'overview';
  const picked = isStaff ? Number(params.get('user')) || undefined : undefined;
  const uid = picked ?? user?.id ?? 0;
  const agents = useQuery({ queryKey: ['users', 'agents-all'], queryFn: () => api.users.list({ role: FIELD_FILTER }), enabled: isStaff });
  const pick = isStaff && (
    <select className="select" style={{ width: 'auto' }} aria-label={t('Чей кабинет')} value={picked ?? ''} onChange={(e) => set('user', e.target.value)}>
      <option value="">{t('Мой кабинет')}</option>
      {itemsOf(agents.data).slice().sort((a, b) => Number(b.is_active !== false) - Number(a.is_active !== false) || (a.name || '').localeCompare(b.name || '')).map((u) => (
        <option key={u.id} value={u.id}>{u.name}{u.is_active === false ? t(' (не работает)') : ''}</option>
      ))}
    </select>
  );
  return (
    <>
      <PageHead label={t('Личный кабинет')} title={t('Кабинет')} actions={pick} />
      <Tabs value={tab} onChange={(t) => set('tab', t === 'overview' ? '' : t)} tabs={TABS} />
      {tab === 'overview' ? <CabinetView userId={picked} tabbed />
        : tab === 'objects' ? <CabinetObjects key={uid} agentId={uid} />
        : tab === 'deals' ? <CabinetDeals key={uid} agentId={uid} />
        : tab === 'contracts' ? <ContractList key={uid} base="/contracts" agentId={picked} label={t('По сделкам')} title={t('Мои договоры')} />
        : tab === 'leads' ? <MyLeadsList agentId={uid} />
        : tab === 'calendar' ? <CalendarView agentId={uid} />
        : <CabinetStats userId={picked} />}
    </>
  );
}
