import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronUp, Copy, Plus, Send, ShieldCheck, Trash2, UserPlus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { itemsOf } from '../api/client';
import type { Invite, InviteStatus, Role, Settings, Source, User } from '../api/types';
import { ADMIN_ROLES, SUPER_ROLES, atLeast } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { errText, useToast } from '../components/toast';
import { Avatar, Badge, Button, Card, Checkbox, Drawer, Empty, ErrorBox, Field, Input, Loading, Modal, PageHead, Seg, Select, Switch, Tabs } from '../components/ui';
import { ROLE_LABEL, ago, fmtDateTime, num, phoneBlur, phoneFocus, phoneInput } from '../lib/format';
import { AvatarEdit, EMAIL_RE, birthdayLabel } from './Cabinet';
import { parseMetrics } from '../lib/useUserNames';
import { ANALYTICS_METRICS, ANALYTICS_SECTIONS } from '../features/deals/Analytics';
import { t } from '../lib/i18n';

const MISSING: Record<string, string> = { name: t('фамилия'), birth_date: t('ДР'), phone: t('телефон'), email: 'email' };
const ROLES: Role[] = ['superadmin', 'admin', 'operator', 'agent', 'recruit', 'daily_rent_manager', 'car_operator'];
const FIELDLESS: Role[] = ['daily_rent_manager', 'car_operator'];  // no level / agent hashtag: only the Daily Rent tab

function UserForm({ user, all, onDone }: { user?: User; all: User[]; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const isSuper = useAuth().hasRole(...SUPER_ROLES);  // backend: only a superadmin grants admin roles
  const [f, setF] = useState<Partial<User>>(user ? { ...user } : { role: 'agent', level: 50, is_active: true, districts: [] });
  const set = <K extends keyof User>(k: K, v: User[K]) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => {
      const body = { first_name: f.first_name?.trim(), last_name: f.last_name?.trim(), role: f.role, level: f.level, is_active: f.is_active, districts: f.districts, mentor_id: f.mentor_id || null,
        tg_id: f.tg_id ? Number(f.tg_id) : null, username: f.username, phone: f.phone, plans: f.plans,
        birth_date: f.birth_date || null, email: f.email?.trim() || null,
        agent_tag: f.agent_tag || '', works_as_agent: !!f.works_as_agent };  // login / password: Telegram-only sign-in, not shown
      return user ? api.users.update(user.id, body) : api.users.create(body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); toast(t('Сохранено')); onDone(); },
    onError: (e) => toast(errText(e), true),
  });
  const promote = useMutation({ mutationFn: () => api.users.promote(user!.id), onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); toast(t('Рекрут переведён в агенты')); onDone(); } });
  const suggest = useMutation({ mutationFn: () => api.users.suggestTag(`${f.first_name || ''} ${f.last_name || ''}`.trim(), user?.id), onSuccess: (r) => set('agent_tag', r.tag), onError: (e) => toast(errText(e), true) });
  const plans = f.plans || { photo: 15, showing: 15, stickers: 15, rental: 15 };
  // required for every employee (Irakli 11-12); the backend checks the same
  const gaps = [!f.first_name?.trim() && t('имя'), !f.last_name?.trim() && t('фамилия'), !f.birth_date && t('дата рождения'),
    (f.phone || '').replace(/\D/g, '').length < 9 && t('телефон'), !EMAIL_RE.test((f.email || '').trim()) && 'email'].filter(Boolean);
  return (
    <div className="col gap-lg">
      {user && <div className="row"><AvatarEdit user={user} size="lg" /><span className="muted" style={{ fontSize: 13 }}>{t('Нажмите на фото, чтобы сменить')}</span></div>}
      <div className="form-grid">
        <Field label={t('Имя *')}><Input value={f.first_name || ''} placeholder={t('Заза')} onChange={(e) => set('first_name', e.target.value)} /></Field>
        <Field label={t('Фамилия *')}><Input value={f.last_name || ''} placeholder={t('Беридзе')} onChange={(e) => set('last_name', e.target.value)} /></Field>
        <Field label={t('Дата рождения *')}><Input type="date" value={f.birth_date || ''} max={new Date().toISOString().slice(0, 10)} onChange={(e) => set('birth_date', e.target.value || null)} /></Field>
        <Field label={t('Email *')} hint={t('Видят только администраторы')}><Input type="email" inputMode="email" value={f.email || ''} placeholder="name@mail.com" onChange={(e) => set('email', e.target.value)} /></Field>
        <Field label={t('Роль')}><Select value={f.role} onChange={(e) => { const r = e.target.value as Role; setF((x) => ({ ...x, role: r, ...(FIELDLESS.includes(r) ? { level: null, works_as_agent: false } : {}) })); }} options={ROLES.filter((r) => isSuper || !ADMIN_ROLES.includes(r) || r === user?.role).map((r) => ({ value: r, label: ROLE_LABEL[r] }))} /></Field>
        {f.role && FIELDLESS.includes(f.role) ? <div /> : <Field label={t('Уровень')}><Seg value={f.level ?? 0} onChange={(v) => set('level', v || null)} options={[{ value: 0, label: '—' }, { value: 50, label: '50%' }, { value: 70, label: '70%' }, { value: 90, label: '90%' }]} /></Field>}
        <Field label="Telegram ID"><Input value={f.tg_id ?? ''} onChange={(e) => set('tg_id', e.target.value ? Number(e.target.value) : null)} inputMode="numeric" /></Field>
        <Field label="@username"><Input value={f.username || ''} onChange={(e) => set('username', e.target.value)} /></Field>
        <Field label={t('Телефон *')}><Input type="tel" value={f.phone || ''} onFocus={phoneFocus} onBlur={phoneBlur} onChange={(e) => set('phone', phoneInput(e))} inputMode="tel" /></Field>
        {f.role && FIELDLESS.includes(f.role) ? <div className="faint" style={{ fontSize: 13, alignSelf: 'center' }}>{t('Видит только «Посуточная аренда»')}</div> : <Field label={t('Хэштег агента')} hint={t('В конце каждого поста: имя латиницей (#Zaza), при совпадении имён + буква фамилии (#ArturB)')}>
          <div className="row gap-sm">
            <Input value={f.agent_tag ? `#${f.agent_tag}` : ''} placeholder="#Zaza" onChange={(e) => set('agent_tag', e.target.value.replace(/^#+/, '') || null)} />
            <Button variant="secondary" size="sm" disabled={!f.first_name?.trim()} loading={suggest.isPending} onClick={() => suggest.mutate()}>{t('Предложить')}</Button>
          </div>
        </Field>}
        {f.role === 'recruit' ? (
          <Field label={t('Наставник')}><Select value={f.mentor_id ?? ''} onChange={(e) => set('mentor_id', e.target.value ? Number(e.target.value) : null)} placeholder="—" options={all.filter((u) => u.role === 'agent' || u.works_as_agent).map((u) => ({ value: u.id, label: u.name }))} /></Field>
        ) : <div />}
      </div>
      {f.role === 'recruit' && (
        <div>
          <span className="label">{t('План на месяц')}</span>
          <div className="grid g4 mt">
            {(['photo', 'showing', 'stickers', 'rental'] as const).map((k) => (
              <Field key={k} label={{ photo: t('Фото'), showing: t('Показы'), stickers: t('Расклейка'), rental: t('Сдачи') }[k]}>
                <Input type="number" value={plans[k]} onChange={(e) => set('plans', { ...plans, [k]: Number(e.target.value) })} />
              </Field>
            ))}
          </div>
        </div>
      )}
      {f.role && atLeast({ role: f.role }, 'operator') && (
        <Switch checked={!!f.works_as_agent} onChange={(v) => set('works_as_agent', v)} label={t('Работает как агент: заявки, свои объекты, рейтинг агентов')} />
      )}
      <Switch checked={!!f.is_active} onChange={(v) => set('is_active', v)} label={t('Активен')} />
      {gaps.length > 0 && <div style={{ color: 'var(--accent)', fontSize: 13, fontWeight: 600 }}>{t('Заполните: {list}', { list: gaps.join(', ') })}</div>}
      <div className="row row-wrap">
        <Button disabled={gaps.length > 0} loading={save.isPending} onClick={() => save.mutate()}>{t('Сохранить')}</Button>
        {user?.role === 'recruit' && <Button variant="secondary" loading={promote.isPending} onClick={() => promote.mutate()}>{t('Перевести в агенты')}</Button>}
      </div>
    </div>
  );
}

const INVITE_STATUS: Record<InviteStatus, [string, 'blue' | 'ok' | 'grey' | 'warn']> = {
  pending: [t('ждёт'), 'blue'], accepted: [t('принят'), 'ok'], expired: [t('истёк'), 'grey'], revoked: [t('отозван'), 'warn'] };

function InviteLinks({ inv }: { inv: Invite }) {
  const toast = useToast();
  const link = inv.bot_link || inv.web_link;
  const copy = (u: string) => navigator.clipboard.writeText(u).then(() => toast(t('Ссылка скопирована')), () => toast(t('Не удалось скопировать'), true));
  const share = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(`Приглашение в CRM Homes in Georgia (${ROLE_LABEL[inv.role]}). Откройте ссылку в Telegram`)}`;
  return (
    <div className="col gap-sm">
      <span className="label">{inv.bot_link ? t('Ссылка в Telegram (откроется бот входа)') : t('Ссылка-приглашение')}</span>
      <div className="row gap-sm"><Input readOnly value={link} onFocus={(e) => e.target.select()} /><Button variant="secondary" size="sm" onClick={() => copy(link)}><Copy size={15} />{t('Копировать')}</Button></div>
      {inv.bot_link && <div className="row gap-sm"><Input readOnly value={inv.web_link} onFocus={(e) => e.target.select()} /><Button variant="secondary" size="sm" onClick={() => copy(inv.web_link)}><Copy size={15} />{t('Веб')}</Button></div>}
      <div className="row row-wrap"><a className="btn" href={share} target="_blank" rel="noreferrer"><Send size={15} />{t('Отправить в Telegram')}</a></div>
      <div className="faint" style={{ fontSize: 12 }}>{t('Одноразовая, действует до {date}. Telegram, который её откроет, станет аккаунтом сотрудника.', { date: fmtDateTime(inv.expires_at) })}</div>
    </div>
  );
}

function InviteForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const isSuper = useAuth().hasRole(...SUPER_ROLES);  // backend: an admin invites up to operator
  const [f, setF] = useState({ role: 'agent' as Role, level: 50 as number | null, agent_tag: '', districts: [] as string[], works_as_agent: false, note: '' });
  const [made, setMade] = useState<Invite | null>(null);
  const create = useMutation({
    mutationFn: () => api.invites.create({ ...f, agent_tag: f.agent_tag || null, note: f.note.trim() || null }),
    onSuccess: (inv) => { qc.invalidateQueries({ queryKey: ['invites'] }); setMade(inv); },
    onError: (e) => toast(errText(e), true),
  });
  if (made) return <div className="col gap-lg"><InviteLinks inv={made} /><div><Button variant="secondary" onClick={onDone}>{t('Готово')}</Button></div></div>;
  return (
    <div className="col gap-lg">
      <div className="form-grid">
        <Field label={t('Кого приглашаем')} className="span2" hint={t('Для списка приглашений, необязательно')}><Input value={f.note} placeholder={t('Нино, новый агент')} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
        <Field label={t('Роль')}><Select value={f.role} onChange={(e) => { const r = e.target.value as Role; setF({ ...f, role: r, ...(FIELDLESS.includes(r) ? { level: null, agent_tag: '', works_as_agent: false } : {}) }); }} options={ROLES.filter((r) => isSuper || !ADMIN_ROLES.includes(r)).map((r) => ({ value: r, label: ROLE_LABEL[r] }))} /></Field>
        {FIELDLESS.includes(f.role) ? <div className="faint" style={{ fontSize: 13, alignSelf: 'center' }}>{t('Видит только «Посуточная аренда»')}</div> : <>
        <Field label={t('Уровень')}><Seg value={f.level ?? 0} onChange={(v) => setF({ ...f, level: v || null })} options={[{ value: 0, label: '—' }, { value: 50, label: '50%' }, { value: 70, label: '70%' }, { value: 90, label: '90%' }]} /></Field>
        <Field label={t('Хэштег агента')} hint={t('Можно задать позже')}><Input value={f.agent_tag ? `#${f.agent_tag}` : ''} placeholder="#Zaza" onChange={(e) => setF({ ...f, agent_tag: e.target.value.replace(/^#+/, '') })} /></Field></>}
      </div>
      {atLeast({ role: f.role }, 'operator') && <Switch checked={f.works_as_agent} onChange={(v) => setF({ ...f, works_as_agent: v })} label={t('Работает как агент')} />}
      <div><Button loading={create.isPending} onClick={() => create.mutate()}><UserPlus size={16} />{t('Создать приглашение')}</Button></div>
    </div>
  );
}

function Invites() {
  const qc = useQueryClient();
  const toast = useToast();
  const [shown, setShown] = useState<Invite | null>(null);
  const { data } = useQuery({ queryKey: ['invites'], queryFn: () => api.invites.list() });
  const revoke = useMutation({ mutationFn: (id: number) => api.invites.revoke(id), onSuccess: () => { qc.invalidateQueries({ queryKey: ['invites'] }); toast(t('Приглашение отозвано')); }, onError: (e) => toast(errText(e), true) });
  const items = data?.items || [];
  if (!items.length) return null;
  return (
    <>
      <h3 style={{ margin: '22px 0 10px' }}>{t('Приглашения')}</h3>
      <div className="card table-wrap">
        <table className="table table-stack">
          <thead><tr><th>{t('Кому')}</th><th>{t('Роль')}</th><th>{t('Статус')}</th><th className="hide-mobile">{t('Создал')}</th><th className="hide-mobile">{t('До')}</th><th /></tr></thead>
          <tbody>{items.map((i) => (
            <tr key={i.id}>
              <td>{i.note || <span className="muted">—</span>}</td>
              <td><Badge tone="blue">{ROLE_LABEL[i.role]}</Badge></td>
              <td><Badge tone={INVITE_STATUS[i.status][1]}>{INVITE_STATUS[i.status][0]}</Badge>{i.used_by && <span className="muted"> {i.used_by.name}</span>}</td>
              <td className="hide-mobile muted">{i.created_by || '—'} · {ago(i.created_at)}</td>
              <td className="hide-mobile muted">{fmtDateTime(i.used_at || i.expires_at)}</td>
              <td>{i.status === 'pending' && <div className="row gap-sm">
                <Button variant="secondary" size="sm" onClick={() => setShown(i)}>{t('Ссылка')}</Button>
                <Button variant="ghost" size="sm" loading={revoke.isPending && revoke.variables === i.id} onClick={() => confirm(t('Отозвать приглашение? Ссылка перестанет работать')) && revoke.mutate(i.id)}>{t('Отозвать')}</Button>
              </div>}</td>
            </tr>))}
          </tbody>
        </table>
      </div>
      <Modal open={!!shown} onClose={() => setShown(null)} title={t('Приглашение')}>{shown && <InviteLinks inv={shown} />}</Modal>
    </>
  );
}

function Users() {
  const [role, setRole] = useState('');
  const [open, setOpen] = useState<User | 'new' | null>(null);
  const [inviting, setInviting] = useState(false);
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['users', 'admin', role], queryFn: () => api.users.list({ role: role || undefined }) });
  const all = useQuery({ queryKey: ['users', 'admin', ''], queryFn: () => api.users.list({}) });
  const toggle = useMutation({ mutationFn: (u: User) => api.users.update(u.id, { is_active: !u.is_active }), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) });
  const toast = useToast();
  const remove = useMutation({ mutationFn: (u: User) => api.users.remove(u.id),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['users'] }); toast(t('Удалён. Объектов передано Платформе: {n}', { n: r.objects_to_platform })); },
    onError: (e) => toast(errText(e), true) });
  const items = itemsOf(data);
  // active on top; the ones who left are folded under «Неактивные (N)» (Stanislav 11-11)
  const [showOff, setShowOff] = useState(false);
  const [gapsOnly, setGapsOnly] = useState(false);
  const shown = gapsOnly ? items.filter((u) => u.profile_missing?.length) : items;
  const active = shown.filter((u) => u.is_active), inactive = shown.filter((u) => !u.is_active);
  const incomplete = items.filter((u) => u.is_active && u.profile_missing?.length).length;
  const row = (u: User) => (
                <tr key={u.id} className="clickable" onClick={() => setOpen(u)}>
                  <td><div className="row"><Avatar name={u.name} src={u.photo_url} />
                    <div><b>{u.name}</b>
                      {u.birthday && <div className="faint" style={{ fontSize: 12 }}>🎂 {birthdayLabel(u.birthday)}</div>}
                      {!!u.profile_missing?.length && <div><Badge tone="warn">{t('нет: {list}', { list: u.profile_missing.map((k) => MISSING[k]).join(', ') })}</Badge></div>}
                    </div></div></td>
                  <td><Badge tone={ADMIN_ROLES.includes(u.role) ? 'solid' : 'blue'}>{ROLE_LABEL[u.role]}</Badge></td>
                  <td className="num">{u.level ? `${u.level}%` : '—'}</td>
                  <td className="muted">{u.agent_tag ? `#${u.agent_tag}` : '—'}</td>
                  <td className="hide-mobile muted">{u.username ? `@${u.username}` : u.tg_id || '—'}</td>
                  <td onClick={(e) => e.stopPropagation()}><div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                    <Switch checked={u.is_active} onChange={() => toggle.mutate(u)} />
                    {!u.is_active && u.role !== 'superadmin' && <Button size="sm" variant="ghost" aria-label={t('Удалить')} title={t('Удалить')} loading={remove.isPending && remove.variables?.id === u.id}
                      onClick={() => confirm(t('Удалить {name}? Пропадёт из списков, его объекты перейдут Платформе. Сделки и история останутся.', { name: u.name })) && remove.mutate(u)}><Trash2 size={14} /></Button>}
                  </div></td>
                </tr>);
  return (
    <>
      <div className="row row-between row-wrap" style={{ marginBottom: 14 }}>
        <Seg value={role} onChange={setRole} options={[{ value: '', label: t('Все') }, ...ROLES.map((r) => ({ value: r, label: ROLE_LABEL[r] }))]} />
        <div className="row row-wrap">
          {incomplete > 0 && <button type="button" className={`chip ${gapsOnly ? 'active' : ''}`} onClick={() => setGapsOnly((v) => !v)}>{t('Не заполнен профиль: {n}', { n: incomplete })}</button>}
          <Button onClick={() => setInviting(true)}><UserPlus size={16} />{t('Пригласить')}</Button>
          <Button variant="secondary" onClick={() => setOpen('new')}><Plus size={16} />{t('Пользователь')}</Button>
          <Link className="btn btn-secondary" to="/ndas"><ShieldCheck size={16} />{t('Соглашение (NDA)')}</Link>
        </div>
      </div>
      {isLoading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <div className="card table-wrap">
          <table className="table table-stack users-table">
            <thead><tr><th>{t('Имя')}</th><th>{t('Роль')}</th><th>{t('Уровень')}</th><th>{t('Хэштег')}</th><th className="hide-mobile">Telegram</th><th>{t('Активен')}</th></tr></thead>
            <tbody>
              {active.map(row)}
              {inactive.length > 0 && (
                <tr className="clickable" onClick={() => setShowOff((v) => !v)}>
                  <td colSpan={7} className="muted" style={{ fontWeight: 700 }}>
                    {showOff ? <ChevronUp size={16} /> : <ChevronDown size={16} />} {t('Неактивные ({n})', { n: inactive.length })} · {showOff ? t('скрыть') : t('показать')}
                  </td>
                </tr>
              )}
              {showOff && inactive.map(row)}
            </tbody>
          </table>
        </div>
      )}
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open === 'new' ? t('Новый пользователь') : (open as User | null)?.name || ''}>
        {open && <UserForm key={open === 'new' ? 'new' : open.id} user={open === 'new' ? undefined : open} all={itemsOf(all.data)} onDone={() => setOpen(null)} />}
      </Drawer>
      <Drawer open={inviting} onClose={() => setInviting(false)} title={t('Пригласить сотрудника')}>
        {inviting && <InviteForm onDone={() => setInviting(false)} />}
      </Drawer>
      <Invites />
    </>
  );
}

/** t.me/<channel> → Telegram channel, facebook.com/groups/<id> → FB group, instagram.com/<user> → Instagram account (the parser reads them on the next run). */
function sourceFromUrl(url: string): { kind: string; key: string } | null {
  const tg = url.match(/t\.me\/(?:s\/)?([\w]+)/i);
  if (tg) return { kind: 'tg_competitor', key: tg[1] };
  const fb = url.match(/facebook\.com\/groups\/([\w.]+)/i);
  if (fb) return { kind: 'fb_group', key: fb[1] };
  const ig = url.match(/instagram\.com\/([\w.]+)/i);
  return ig ? { kind: 'ig_account', key: ig[1] } : null;
}

const EVERY = [15, 30, 60, 120, 180, 360, 480, 720, 1440].map((m) => ({ value: m, label: m < 60 ? t('раз в {m} мин', { m }) : m === 1440 ? t('раз в сутки') : t('раз в {h} ч', { h: m / 60 }) }));
const usd = (n: number) => `$${n < 10 ? n.toFixed(2) : Math.round(n)}`;

/** Per-source parser frequency; a paid (Apify) source shows its price a month at the chosen frequency. */
function Schedule() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data } = useQuery({ queryKey: ['sources-schedule'], queryFn: api.sources.schedule });
  const save = useMutation({
    mutationFn: (b: Record<string, number>) => api.sources.setSchedule(b),
    onSuccess: (d) => { qc.setQueryData(['sources-schedule'], d); toast(t('Расписание сохранено, парсер подхватит его со следующего круга')); },
    onError: (e) => toast(errText(e), true),
  });
  if (!data) return null;
  return (
    <Card title={t('Как часто парсить')}>
      {data.map((s) => {
        const runs = (30 * 1440) / s.every_min;
        const p = s.paid;
        const month = p ? runs * p.per_run + (p.per_hour ?? 0) * 720 : 0;
        const opts = EVERY.some((o) => o.value === s.every_min) ? EVERY : [...EVERY, { value: s.every_min, label: t('раз в {m} мин', { m: s.every_min }) }];
        return (
          <div key={s.key} className="list-row">
            <span className="grow">{s.label}</span>
            {p ? (
              <span className="muted" style={{ fontSize: 12, textAlign: 'right' }}>
                <b>≈ {usd(month)}{t('/мес')}</b>{p.per_hour === null && t(' + посты')}<br />
                {t('за 7 дней: {spent}, {runs} запусков, {posts} постов', { spent: usd(p.spent_7d), runs: p.runs_7d, posts: p.posts_7d })}
              </span>
            ) : <span className="faint" style={{ fontSize: 12 }}>{t('бесплатно')}</span>}
            <Select style={{ width: 150 }} value={s.every_min} onChange={(e) => save.mutate({ [s.key]: Number(e.target.value) })} options={opts} />
          </div>
        );
      })}
      <div className="faint mt" style={{ fontSize: 12 }}>{t('Apify: Facebook $0.002 за запуск + $0.0007 за новый пост (посты приходят сами, частота меняет только число запусков), Threads $0.03 за поисковый запрос в каждом запуске.')}</div>
    </Card>
  );
}

function Sources() {
  const qc = useQueryClient();
  const toast = useToast();
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const { data, isLoading, error } = useQuery({ queryKey: ['sources'], queryFn: api.sources.list });
  const upd = useMutation({ mutationFn: ({ id, ...b }: Partial<Source> & { id: number | string }) => api.sources.update(id, b), onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }), onError: (e) => toast(errText(e), true) });
  const parsed = sourceFromUrl(url.trim());
  const add = useMutation({
    mutationFn: () => api.sources.create({ ...parsed!, url: url.trim(), name: name.trim() || undefined, enabled: true } as never),
    onSuccess: () => { setUrl(''); setName(''); qc.invalidateQueries({ queryKey: ['sources'] }); toast(t('Источник добавлен, парсер заберёт его при следующем запуске')); },
    onError: (e) => toast(errText(e), true),
  });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const items = itemsOf(data);
  return (
    <div className="col gap-lg">
      <Schedule />
      <Card title={t('Добавить источник')}>
        <div className="row row-wrap" style={{ alignItems: 'flex-end' }}>
          <Field label={t('Ссылка на Telegram-канал, группу Facebook или Instagram-аккаунт')} className="grow"><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder={t('https://t.me/channel, https://facebook.com/groups/123 или https://instagram.com/user')} /></Field>
          <Field label={t('Название (необязательно)')}><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Button disabled={!parsed} loading={add.isPending} onClick={() => add.mutate()}><Plus size={16} />{t('Добавить')}</Button>
        </div>
        {url.trim() && !parsed && <div className="muted mt" style={{ fontSize: 12 }}>{t('Нужна ссылка вида t.me/… или facebook.com/groups/…')}</div>}
        {parsed && <div className="muted mt" style={{ fontSize: 12 }}>{({ fb_group: t('Группа Facebook'), ig_account: t('Instagram-аккаунт') } as Record<string, string>)[parsed.kind] || t('Telegram-канал')}: {parsed.key}</div>}
      </Card>
      {!items.length ? <Empty text={t('Источников нет')} /> : (
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
          {items.map((s) => (
            <div key={s.id} className="card card-pad col">
              <div className="row row-between"><h3>{s.name || (s as { key?: string }).key || s.kind}</h3><Switch checked={s.enabled} onChange={(v) => upd.mutate({ id: s.id, enabled: v })} /></div>
              <div className="muted ellipsis" style={{ fontSize: 13 }}>{s.url || s.kind}</div>
              <div className="row gap-sm">{s.count !== undefined && <Badge tone="grey">{t('{n} объявлений', { n: s.count })}</Badge>}{s.last_run_at && <Badge tone="grey">{ago(s.last_run_at)}</Badge>}</div>
              {/* our own agency channel can't be a competitor */}
              {s.kind !== 'tg_agency' && (
                <div className="row row-between row-wrap gap-sm">
                  <Checkbox checked={!!s.options?.competitor} title={t('Объявления этого источника не попадут в «Новые объявления»: только в «Объекты → База → Конкуренты», при первом запуске парсер загрузит всю его историю')}
                    onChange={(v) => upd.mutate({ id: s.id, options: { ...s.options, competitor: v } })}>{t('Конкурент')}</Checkbox>
                  {s.options?.competitor && (s.options.backfilled_at
                    ? <Badge tone="grey">{t('история загружена {d}', { d: fmtDateTime(s.options.backfilled_at) })}</Badge>
                    : <Badge tone="blue" title={t('история загрузится при следующем запуске')}>{t('история загрузится')}</Badge>)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TickerAdmin() {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const { data } = useQuery({ queryKey: ['ticker'], queryFn: api.ticker.list });
  const add = useMutation({ mutationFn: () => api.ticker.create(text), onSuccess: () => { setText(''); qc.invalidateQueries({ queryKey: ['ticker'] }); } });
  const del = useMutation({ mutationFn: (id: number) => api.ticker.remove(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['ticker'] }) });
  return (
    <Card label={t('Главная')} title={t('Бегущая строка')}>
      <div className="row" style={{ marginBottom: 12 }}>
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t('Текст сообщения, без восклицательных знаков')} />
        <Button disabled={!text.trim()} loading={add.isPending} onClick={() => add.mutate()}><Plus size={16} />{t('Добавить')}</Button>
      </div>
      {itemsOf(data).map((tk) => (
        <div key={tk.id} className="list-row">
          <span className="grow">{tk.text}</span><span className="faint" style={{ fontSize: 12 }}>{fmtDateTime(tk.created_at)}</span>
          <Button size="sm" variant="ghost" onClick={() => del.mutate(tk.id)} aria-label={t('Удалить')}><Trash2 size={14} /></Button>
        </div>
      ))}
    </Card>
  );
}

const METRICS: [string, string][] = [['deals', t('Сделки')], ['platform', t('Комиссия платформы')], ['active_objects', t('Активные объекты')], ['reposts', t('Репосты')],
  ['leaderboard', t('Топ-5 агентов')], ['telegram_top', t('Telegram топ-10')], ['funnel', t('Объекты и заявки по этапам')], ['response_times', t('Время реакции')]];

/** The operator's Telegram account for the userbot (DMs with clients, slot cards): log in by a QR code from here. */
function OperatorAccount() {
  const qc = useQueryClient();
  const toast = useToast();
  const [pw, setPw] = useState('');
  const { data: st } = useQuery({
    queryKey: ['userbot'], queryFn: api.userbot.status,
    refetchInterval: (q) => (['starting', 'qr', 'password'].includes(q.state.data?.login?.status || '') ? 2000 : false),
  });
  const set = (d: unknown) => qc.setQueryData(['userbot'], d);
  const login = useMutation({ mutationFn: api.userbot.login, onSuccess: set, onError: (e) => toast(errText(e), true) });
  const send = useMutation({ mutationFn: () => api.userbot.password(pw), onSuccess: (d) => { setPw(''); set(d); }, onError: (e) => toast(errText(e), true) });
  const logout = useMutation({ mutationFn: api.userbot.logout, onSuccess: (d) => { set(d); toast(t('Аккаунт оператора отключён')); }, onError: (e) => toast(errText(e), true) });
  if (!st) return <Card label="Telegram" title={t('Аккаунт оператора')}><Loading /></Card>;
  const l = st.login?.status;
  let body;
  if (!st.configured) body = <div className="muted">{t('Сервис userbot не настроен: на сервере нужен USERBOT_URL и сервис userbot (docs/DEPLOY.md).')}</div>;
  else if (!st.reachable) body = <div className="muted">{t('Сервис userbot не отвечает. Если он только что перезапустился, обновите страницу через минуту.')}</div>;
  else if (!st.enabled) body = <div className="muted">{t('На сервере не заданы API_ID и API_HASH (my.telegram.org).')}</div>;
  else if (st.authorized && st.me) body = (
    <div className="col gap-sm">
      <div>{t('Подключён:')} <b>{st.me.name}</b>{st.me.username && <span className="muted"> @{st.me.username}</span>}</div>
      <div className="muted" style={{ fontSize: 12 }}>{t('С этого аккаунта уходят сообщения клиентам и карточки времени просмотра, его входящие попадают в заявки.')}</div>
      <div><Button variant="secondary" loading={logout.isPending} onClick={() => { if (confirm(t('Отключить аккаунт оператора? Сеанс завершится в Telegram, сообщения клиентам перестанут уходить.'))) logout.mutate(); }}>{t('Отключить')}</Button></div>
    </div>
  );
  else if (l === 'qr' && st.login?.qr_svg) body = (
    <div className="col gap-sm">
      <div style={{ width: 220, background: '#fff', borderRadius: 8 }} dangerouslySetInnerHTML={{ __html: st.login.qr_svg }} />
      <div className="muted" style={{ fontSize: 13 }}>{t('На телефоне оператора: Telegram → Настройки → Устройства → Подключить устройство, наведите камеру на код. Код обновляется сам.')}</div>
    </div>
  );
  else if (l === 'password') body = (
    <div className="col gap-sm">
      <div>{t('У аккаунта включён облачный пароль. Пусть оператор введёт его сам:')}</div>
      <div className="row">
        <Input type="password" autoComplete="off" value={pw} onChange={(e) => setPw(e.target.value)} placeholder={t('Облачный пароль Telegram')} onKeyDown={(e) => { if (e.key === 'Enter' && pw) send.mutate(); }} />
        <Button disabled={!pw} loading={send.isPending} onClick={() => send.mutate()}>{t('Войти')}</Button>
      </div>
      {st.login?.error === 'wrong_password' && <div style={{ color: 'var(--danger, #c00)', fontSize: 13 }}>{t('Неверный пароль')}</div>}
      <div className="faint" style={{ fontSize: 12 }}>{t('Пароль сразу уходит в Telegram и нигде не сохраняется.')}</div>
    </div>
  );
  else body = (
    <div className="col gap-sm">
      {l === 'expired' && <div className="muted">{t('Время на вход вышло (5 минут), начните заново.')}</div>}
      {l === 'error' && <div className="muted">{t('Не получилось войти ({e}), попробуйте ещё раз.', { e: st.login?.error ?? '' })}</div>}
      {l === 'done' || l === 'starting' ? <Loading /> : <>
        <div className="muted" style={{ fontSize: 13 }}>{t('Аккаунт не подключён: клиентам не уходят сообщения от оператора. Подключите аккаунт оператора по QR-коду.')}</div>
        <div><Button loading={login.isPending} onClick={() => login.mutate()}>{t('Подключить по QR-коду')}</Button></div>
      </>}
    </div>
  );
  return <Card label="Telegram" title={t('Аккаунт оператора')}>{body}</Card>;
}

function SettingsAdmin() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data, isLoading, error } = useQuery({ queryKey: ['settings'], queryFn: api.settings.get });
  const [s, setS] = useState<Settings>({});
  useEffect(() => { if (data) setS(data); }, [data]);
  const save = useMutation({ mutationFn: () => api.settings.put(s), onSuccess: () => { qc.invalidateQueries({ queryKey: ['settings'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }); toast(t('Настройки сохранены')); }, onError: (e) => toast(errText(e), true) });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const str = (k: string) => (s[k] === undefined || s[k] === null ? '' : String(s[k]));
  const setK = (k: string, v: unknown) => setS({ ...s, [k]: v });
  const metrics = parseMetrics(s.dashboard_metrics) || Object.fromEntries([...METRICS, ...ANALYTICS_METRICS].map(([k]) => [k, true]));
  // metrics saved before the analytics tab existed have no an_* keys: treat those as on
  if (!Object.keys(metrics).some((k) => k.startsWith('an_'))) ANALYTICS_METRICS.forEach(([k]) => { metrics[k] = true; });
  const sections = parseMetrics(s.dashboard_sections) || Object.fromEntries(ANALYTICS_SECTIONS.map(([k]) => [k, true]));
  const setSection = (k: string, on: boolean) => {
    const next = { ...sections, [k]: on };
    setK('dashboard_sections', JSON.stringify(Object.keys(next).filter((x) => next[x])));
  };
  const setMetric = (k: string, on: boolean) => {
    const next = { ...metrics, [k]: on };
    setK('dashboard_metrics', JSON.stringify(Object.keys(next).filter((x) => next[x])));
  };
  return (
    <div className="grid g2">
      <OperatorAccount />
      <Card label={t('Заявки')} title={t('Сроки (SLA), минуты')}>
        <div className="col" style={{ marginBottom: 12 }}>
          <Switch checked={str('sla_enabled') !== '0'} onChange={(v) => setK('sla_enabled', v ? '1' : '0')} label={t('SLA включён')} />
          <div className="muted" style={{ fontSize: 12 }}>{t('Выключите — у заявок пропадут таймеры, напоминания и эскалации по срокам. Включите — сроки снова считаются с ближайшего шага заявки.')}</div>
        </div>
        <div className="form-grid">
          <Field label={t('Оператор берёт заявку')}><Input type="number" value={str('sla_operator_take_min')} onChange={(e) => setK('sla_operator_take_min', e.target.value)} /></Field>
          <Field label={t('Агент вводит время')}><Input type="number" value={str('sla_agent_slots_min')} onChange={(e) => setK('sla_agent_slots_min', e.target.value)} /></Field>
          <Field label={t('Время клиенту')}><Input type="number" value={str('sla_slots_to_client_min')} onChange={(e) => setK('sla_slots_to_client_min', e.target.value)} /></Field>
          <Field label={t('Обещание клиенту')}><Input type="number" value={str('client_promise_min')} onChange={(e) => setK('client_promise_min', e.target.value)} /></Field>
          <Field label={t('План сделок в месяц')}><Input type="number" value={str('deals_plan')} onChange={(e) => setK('deals_plan', e.target.value)} /></Field>
        </div>
      </Card>
      <Card label={t('Объекты')} title={t('Фото и видео')}>
        <div className="col">
          <Switch checked={str('room_picker') !== '0'} onChange={(v) => setK('room_picker', v ? '1' : '0')} label={t('Выбор комнаты под фото (необязательный)')} />
          <div className="muted" style={{ fontSize: 12 }}>{t('Выключите, чтобы агенты не видели выбор комнаты и «Что снято». Отправку на модерацию комнаты не блокируют в любом случае.')}</div>
        </div>
      </Card>
      <Card label={t('Главная')} title={t('Метрики дашборда')}>
        <div className="col">
          {METRICS.map(([k, label]) => <Switch key={k} checked={!!metrics[k]} onChange={(v) => setMetric(k, v)} label={label} />)}
          {/* «Статистика»: stored as an opt-out so lists saved before it existed keep it on */}
          <Switch checked={!metrics.stats_off} onChange={(v) => setMetric('stats_off', !v)} label={t('Статистика (объекты, заявки, сделки)')} />
        </div>
      </Card>
      <Card label={t('Сделки → Аналитика')} title={t('Метрики аналитики')}>
        <div className="col">
          {ANALYTICS_METRICS.map(([k, label]) => <Switch key={k} checked={!!metrics[k]} onChange={(v) => setMetric(k, v)} label={label} />)}
        </div>
      </Card>
      <Card label={t('Сделки → Аналитика')} title={t('Секции дашборда')}>
        <div className="col">
          <div className="label">{t('Канал и объекты')}</div>
          {ANALYTICS_SECTIONS.slice(0, 3).map(([k, label]) => <Switch key={k} checked={!!sections[k]} onChange={(v) => setSection(k, v)} label={label} />)}
          <div className="label mt">{t('Платформа и сделки')}</div>
          {ANALYTICS_SECTIONS.slice(3).map(([k, label]) => <Switch key={k} checked={!!sections[k]} onChange={(v) => setSection(k, v)} label={label} />)}
        </div>
      </Card>
      <div><Button size="lg" loading={save.isPending} onClick={() => save.mutate()}>{t('Сохранить настройки')}</Button></div>
    </div>
  );
}

/** Integration keys (superadmin): Apify, AI, maps… entered here win over the server's .env, no restart (backend app/keys.py).
 *  A value is never shown again: only where it comes from and its last 4 characters. */
function KeysAdmin() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['keys'], queryFn: api.keys.list });
  const [edit, setEdit] = useState<{ name: string; value: string; isNew?: boolean; custom?: boolean } | null>(null);
  const done = (d: { items: unknown[] }) => { qc.setQueryData(['keys'], d); setEdit(null); toast(t('Сохранено')); };
  const put = useMutation({ mutationFn: () => api.keys.put(edit!.name.trim().toUpperCase(), edit!.value.trim()), onSuccess: done, onError: (e) => toast(errText(e), true) });
  const del = useMutation({ mutationFn: (n: string) => api.keys.remove(n), onSuccess: (d) => qc.setQueryData(['keys'], d), onError: (e) => toast(errText(e), true) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <Card label={t('Только для администраторов')} title={t('Ключи интеграций')}>
      <p className="muted" style={{ marginTop: 0 }}>{t('Ключ из CRM главнее ключа на сервере и начинает работать в течение минуты, без перезапуска. Значение после сохранения больше не показывается.')}</p>
      {itemsOf(q.data).map((k) => (
        <div key={k.name} className="list-row" style={{ flexWrap: 'wrap' }}>
          <div className="grow" style={{ minWidth: 220 }}>
            <div style={{ fontWeight: 700 }}>{k.title ? t(k.title) : k.name}</div>
            <div className="muted" style={{ fontSize: 12 }}>{k.note ? `${t(k.note)} · ` : ''}<span style={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}>{k.name}</span></div>
          </div>
          {k.source === 'crm' ? <Badge tone="ok">{t('CRM')} · …{k.tail}</Badge> : k.source === 'env' ? <Badge tone="grey">{t('сервер')} · …{k.tail}</Badge> : <Badge tone="warn">{t('не задан')}</Badge>}
          <Button size="sm" variant="secondary" onClick={() => setEdit({ name: k.name, value: '' })}>{k.source === 'crm' ? t('Заменить') : t('Задать')}</Button>
          {k.source === 'crm' && <Button size="sm" variant="ghost" aria-label={t('Удалить')} loading={del.isPending && del.variables === k.name} onClick={() => confirm(t('Удалить ключ {name} из CRM? Останется значение с сервера, если оно есть.', { name: k.name })) && del.mutate(k.name)}><Trash2 size={14} /></Button>}
        </div>
      ))}
      <div className="row mt"><Button variant="secondary" onClick={() => setEdit({ name: '', value: '', isNew: true })}><Plus size={16} />{t('Добавить ключ')}</Button></div>
      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.isNew ? t('Новый ключ') : t(itemsOf(q.data).find((k) => k.name === edit?.name)?.title || edit?.name || '')}>
        {edit && <form className="col gap" onSubmit={(e) => { e.preventDefault(); put.mutate(); }}>
          {edit.isNew && <Field label={t('Какой ключ')}><Select value={edit.custom ? '_' : edit.name}
            onChange={(e) => setEdit({ ...edit, name: e.target.value === '_' ? '' : e.target.value, custom: e.target.value === '_' })}
            placeholder={t('Выберите…')}
            options={[...itemsOf(q.data).filter((k) => k.title).map((k) => ({ value: k.name, label: t(k.title!) })), { value: '_', label: t('Другой ключ (ввести имя)') }]} /></Field>}
          {edit.isNew && edit.custom && <Field label={t('Имя ключа латиницей, например THREADS_TOKEN')}><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '') })} required /></Field>}
          <Field label={t('Значение')}><Input type="password" autoComplete="off" value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} required /></Field>
          <Button type="submit" loading={put.isPending} disabled={!edit.name.trim() || !edit.value.trim()}>{t('Сохранить')}</Button>
        </form>}
      </Modal>
    </Card>
  );
}

/** What Apify and the AI cost (superadmin): Apify runs the parser recorded + each key's month from Apify; AI tokens the
 *  bot/parser recorded per call (bot/llm.py), $ estimated at OpenAI prices (backend /spend). */
function SpendCard() {
  const q = useQuery({ queryKey: ['spend'], queryFn: api.spend });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const { apify, ai } = q.data!;
  const usd = (v: number | null | undefined) => (v == null ? '—' : `$${v.toFixed(2)}`);
  const sum = (x: typeof ai.today) => `${usd(x.usd)} · ${t('{calls} вызовов, {tokens} токенов', { calls: num(x.calls), tokens: num(x.prompt + x.completion) })}`;
  const bySource = Object.entries(apify.by_source_week).map(([k, v]) => `${k} ${usd(v)}`).join(', ');
  return (
    <Card label={t('Только для администраторов')} title={t('Расходы')}>
      <div className="label">{t('Apify (парсеры)')}</div>
      <div className="list-row"><span className="grow">{t('Сегодня')}</span><b>{usd(apify.today_usd)}</b></div>
      <div className="list-row"><span className="grow">{t('За 7 дней')}{bySource ? ` (${bySource})` : ''}</span><b>{usd(apify.week_usd)}</b></div>
      {apify.accounts.length === 0 && <p className="muted">{t('Ключей Apify нет')}</p>}
      {apify.accounts.map((a) => (
        <div key={a.tail} className="list-row">
          <span className="grow">{t('Ключ')} <span style={{ fontFamily: 'monospace' }}>…{a.tail}</span>{a.cycle_end ? ` · ${t('месяц до {date}', { date: a.cycle_end })}` : ''}</span>
          {a.error ? <Badge tone="warn">{a.error === 'invalid_key' ? t('ключ не работает') : t('Apify не отвечает')}</Badge>
            : <b>{usd(a.used_usd)}{a.limit_usd != null ? ` ${t('из')} ${usd(a.limit_usd)}` : ''}</b>}
        </div>
      ))}
      <div className="label mt">{t('ИИ (нейросеть)')} · <span style={{ fontFamily: 'monospace' }}>{ai.model}</span></div>
      {ai.provider !== 'openai' && <p className="muted">{t('Сейчас ИИ идёт через подписку Codex: токены не считаются')}</p>}
      <div className="list-row"><span className="grow">{t('Сегодня')}</span><b>{sum(ai.today)}</b></div>
      <div className="list-row"><span className="grow">{t('За месяц')}</span><b>{sum(ai.month)}</b></div>
      <p className="muted" style={{ fontSize: 12 }}>
        {ai.balance_rub != null ? t('Баланс ProxyAPI: {rub} ₽', { rub: num(Math.round(ai.balance_rub)) }) : t('Баланс ProxyAPI этот ключ не показывает, он виден в кабинете proxyapi.ru')}
        {' · '}{t('$ примерно, по ценам OpenAI; ProxyAPI списывает рубли со своей наценкой')}
        {[...new Set([...ai.today.unpriced, ...ai.month.unpriced])].map((m) => ` · ${t('нет цены для {m}', { m })}`)}
      </p>
    </Card>
  );
}

export function AdminPage() {
  const [tab, setTab] = useState<'users' | 'sources' | 'ticker' | 'settings' | 'keys'>('users');
  return (
    <>
      <PageHead label={t('Только для администраторов')} title={t('Управление')} />
      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'users', label: t('Пользователи') }, { value: 'sources', label: t('Источники') },
        { value: 'ticker', label: t('Бегущая строка') }, { value: 'settings', label: t('Настройки') },
        { value: 'keys', label: t('Ключи') },
      ]} />
      {tab === 'users' && <Users />}
      {tab === 'sources' && <Sources />}
      {tab === 'ticker' && <TickerAdmin />}
      {tab === 'settings' && <SettingsAdmin />}
      {tab === 'keys' && <><SpendCard /><KeysAdmin /></>}
    </>
  );
}
