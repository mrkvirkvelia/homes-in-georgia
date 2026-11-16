import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Building2, Cake, CircleUser, Clock, Coins, Handshake, Repeat2, Send } from 'lucide-react';
import { api } from '../api';
import { itemsOf } from '../api/client';
import type { Lead, Property } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { SlaChip, LeadStatusBadge, PropertyStatusBadge } from '../components/domain';
import { Avatar, Card, Empty, ErrorBox, Loading, PageHead, Progress, Stat } from '../components/ui';
import { parseMetrics } from '../lib/useUserNames';
import { LEAD_BOARD, LEAD_STATUS, PROPERTY_BOARD, PROPERTY_STATUS, fmtSlot, money, nextLevelAt, num } from '../lib/format';
import { lx, t } from '../lib/i18n';

function FunnelRow({ order, labels, counts, link }: { order: string[]; labels: Record<string, string>; counts?: Record<string, number>; link: string }) {
  const max = Math.max(1, ...order.map((k) => counts?.[k] || 0));
  return (
    <div className="col gap-sm">
      {order.map((k) => (
        <Link key={k} to={link} className="row" style={{ color: 'inherit', textDecoration: 'none' }}>
          <span style={{ width: 132, fontSize: 12, fontWeight: 600 }} className="muted ellipsis">{labels[k]}</span>
          <div className="grow" style={{ height: 18, background: 'var(--brand-tint)', borderRadius: 6, overflow: 'hidden' }}>
            <div style={{ width: `${((counts?.[k] || 0) / max) * 100}%`, height: '100%', background: k === 'refused' ? 'var(--faint)' : 'var(--brand)', borderRadius: 6, minWidth: counts?.[k] ? 4 : 0 }} />
          </div>
          <span className="num" style={{ width: 28, textAlign: 'right', fontWeight: 800 }}>{counts?.[k] || 0}</span>
        </Link>
      ))}
    </div>
  );
}

type Stats = {
  scope: 'agency' | 'mine';
  objects: Record<'work' | 'review' | 'published' | 'rented' | 'archived' | 'feed_today' | 'feed_week', number>;
  leads: Record<'new' | 'work' | 'viewings_today' | 'rented_month', number>;
  deals: { month: number; prev_month: number };
  contracts_expiring: number;
};

function N({ to, n, label, sub }: { to: string; n: number; label: string; sub?: React.ReactNode }) {
  return (
    <Link to={to} className="card" style={{ padding: '10px 12px', color: 'inherit', textDecoration: 'none', minWidth: 0, overflowWrap: 'anywhere' }}>
      <div className="num" style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.1 }}>{num(n)}{sub}</div>
      <div className="muted" style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.25, marginTop: 2 }}>{label}</div>
    </Link>
  );
}

/** «Статистика» (Stanislav 11-11): where everything is, each number opens its list. Backend analytics.stats. */
function StatsBlock({ s, staff }: { s: Stats; staff: boolean }) {
  const o = s.objects, l = s.leads, d = s.deals.month - s.deals.prev_month;
  const row = (title: string, items: React.ReactNode) => (
    <div className="col gap-sm">
      <div className="label">{title}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(124px, 1fr))', gap: 8 }}>{items}</div>
    </div>
  );
  return (
    <Card label={t('Статистика')} title={s.scope === 'mine' ? t('Мои цифры') : t('По агентству')}>
      <div className="col gap-lg">
        {row(t('Объекты'), <>
          <N to="/objects?tab=board" n={o.work} label={t('в работе')} />
          <N to={staff ? '/objects?tab=review' : '/objects?tab=board'} n={o.review} label={t('на публикации')} />
          <N to="/objects?tab=all&status=published" n={o.published} label={t('опубликовано')} />
          <N to="/objects?tab=all&status=rented" n={o.rented} label={t('сдано')} />
          <N to="/objects?tab=archive" n={o.archived} label={t('в архиве')} />
          <N to="/objects?tab=new" n={o.feed_today} label={t('новых сегодня')} />
          <N to="/objects?tab=new" n={o.feed_week} label={t('новых за 7 дней')} />
        </>)}
        {row(t('Заявки'), <>
          <N to="/leads" n={l.new} label={t('новые')} />
          <N to="/leads" n={l.work} label={t('в работе')} />
          <N to="/calendar" n={l.viewings_today} label={t('просмотры сегодня')} />
          <N to="/leads" n={l.rented_month} label={t('сданы за месяц')} />
        </>)}
        {row(t('Сделки и договоры'), <>
          <N to="/deals" n={s.deals.month} label={t('сделок за месяц')}
            sub={d ? <span style={{ fontSize: 12, marginLeft: 6, color: d > 0 ? 'var(--brand)' : 'var(--accent)' }}>{d > 0 ? '↑' : '↓'}{Math.abs(d)}</span> : undefined} />
          <N to="/deals" n={s.deals.prev_month} label={t('за прошлый месяц')} />
          <N to={staff ? '/reports?tab=expiring' : '/me'} n={s.contracts_expiring} label={t('договоры кончаются ≤30 дн')} />
        </>)}
      </div>
    </Card>
  );
}

function TaskRow({ to, title, meta, right }: { to: string; title: string; meta?: string; right?: React.ReactNode }) {
  return (
    <Link to={to} className="list-row" style={{ color: 'inherit', textDecoration: 'none' }}>
      <div className="grow">
        <div style={{ fontWeight: 700 }} className="ellipsis">{title}</div>
        {meta && <div className="muted" style={{ fontSize: 12 }}>{meta}</div>}
      </div>
      {right}
      <ArrowRight size={16} color="var(--faint)" />
    </Link>
  );
}

/** agent: a staff member's own agent tasks (works_as_agent) (his leads / objects) next to the staff queue. */
function MyTasks({ agent = false }: { agent?: boolean }) {
  const { user, isStaff: staff } = useAuth();
  const isStaff = staff && !agent;
  const leads = useQuery({ queryKey: ['leads', 'list', isStaff ? 'all' : 'mine'], queryFn: () => api.leads.list(isStaff ? {} : { agent_id: user?.id }) });
  const props = useQuery({ queryKey: ['properties', 'list', isStaff ? 'review' : 'mine'], queryFn: () => api.properties.list(isStaff ? { status: 'review' } : { mine: 1 }) });
  const ls = itemsOf(leads.data);
  const ps = itemsOf(props.data);

  let leadTasks: Lead[];
  let propTasks: Property[];
  if (isStaff) {
    leadTasks = ls.filter((l) => ['new', 'operator_taken', 'viewing_done', 'deal_pending'].includes(l.status) || (l.sla_due_at && new Date(l.sla_due_at).getTime() < Date.now()));
    propTasks = ps.filter((p) => p.status === 'review');
  } else {
    leadTasks = ls.filter((l) => ['agent_assigned', 'time_chosen', 'viewing_done'].includes(l.status));
    propTasks = ps.filter((p) => ['taken', 'call_failed', 'owner_confirmed', 'shoot_scheduled', 'returned', 'media_uploaded'].includes(p.status));
  }
  const total = leadTasks.length + propTasks.length;

  return (
    <Card label={agent ? t('Мои задачи · агент') : t('Мои задачи')} title={total ? t('{n} в работе', { n: total }) : t('Всё сделано')}>
      {leads.isLoading || props.isLoading ? <Loading /> : total === 0 ? <Empty text={t('Срочных задач нет')} /> : (
        <div>
          {leadTasks.slice(0, 6).map((l) => (
            <TaskRow key={`l${l.id}`} to={`/leads/${l.id}`} title={`${t('Заявка #{id}', { id: l.id })} · ${l.listing?.title || ''}`}
              meta={l.status === 'agent_assigned' && !isStaff ? t('Введите свободное время') : l.status === 'new' ? t('Возьмите заявку') : l.viewing_at ? t('Просмотр {d}', { d: fmtSlot(l.viewing_at) }) : LEAD_STATUS[l.status]}
              right={l.sla_due_at ? <SlaChip lead={l} /> : <LeadStatusBadge status={l.status} />} />
          ))}
          {propTasks.slice(0, 6).map((p) => (
            <TaskRow key={`p${p.id}`} to={`/objects/${p.id}`} title={`${p.district || ''} · ${p.address || t('Объект #{id}', { id: p.id })}`}
              meta={isStaff ? t('Проверить и опубликовать') : p.status === 'call_failed' ? t('Перезвонить собственнику') : p.status === 'returned' ? p.review_comment || t('Возвращён на доработку') : PROPERTY_STATUS[p.status]}
              right={<PropertyStatusBadge status={p.status} />} />
          ))}
        </div>
      )}
    </Card>
  );
}

const MONTHS = lx(['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'],
  ['იანვარი', 'თებერვალი', 'მარტი', 'აპრილი', 'მაისი', 'ივნისი', 'ივლისი', 'აგვისტო', 'სექტემბერი', 'ოქტომბერი', 'ნოემბერი', 'დეკემბერი'],
  ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']);

/** «Дни рождения» (Irakli 11-12): today and the next 7 days; the age only comes for admins. */
function Birthdays() {
  const { data } = useQuery({ queryKey: ['birthdays'], queryFn: api.birthdays });
  const items = data?.items || [];
  return (
    <Card label={t('Команда')} title={t('Дни рождения')}>
      {items.length === 0 ? <Empty text={t('В ближайшую неделю нет')} /> : items.map((b) => (
        <div key={b.id} className="list-row">
          <Avatar name={b.name} src={b.photo_url} />
          <div className="grow">
            <b>{b.name}</b>
            <div className="muted" style={{ fontSize: 12 }}>{b.day} {MONTHS[b.month - 1]}{b.age ? ` · ${t('{n} лет', { n: b.age })}` : ''}</div>
          </div>
          {b.days_left === 0 ? <span className="badge" style={{ background: 'var(--accent)', color: '#fff' }}><Cake size={12} /> {t('сегодня')}</span>
            : <span className="badge">{b.days_left === 1 ? t('завтра') : t('через {n} дн', { n: b.days_left })}</span>}
        </div>
      ))}
    </Card>
  );
}

export function DashboardPage() {
  const { user, isStaff } = useAuth();
  const { data, isLoading, error } = useQuery({ queryKey: ['dashboard'], queryFn: api.analytics.dashboard, refetchInterval: 60_000 });
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings.get, retry: false });
  const metrics = parseMetrics(settings.data?.dashboard_metrics) || parseMetrics(data?.metrics);
  const ALIAS: Record<string, string[]> = { deals: ['deals'], commission: ['platform', 'commission'], objects: ['active_objects', 'objects'],
    reposts: ['reposts'], top_agents: ['leaderboard', 'top_agents'], telegram_top: ['telegram_top'], funnel: ['funnel'], response_times: ['response_times'] };
  const show = (k: string) => !metrics || (ALIAS[k] || [k]).some((a) => metrics[a]);
  const rt = data?.response_times as { operator_take_avg_min?: number | null; agent_slots_avg_min?: number | null } | undefined;
  const target = Number(settings.data?.deals_plan || (data as Record<string, unknown> | undefined)?.deals_plan || 0);

  return (
    <>
      <PageHead label={t('Добрый день, {name}', { name: user?.name || '' })} title={t('Главная')} />
      {!!user?.profile_missing?.length && (
        <Link to="/me" className="card row" style={{ padding: '10px 14px', marginBottom: 14, color: 'inherit', textDecoration: 'none', borderColor: 'var(--accent)' }}>
          <span className="grow"><b>{t('Заполните профиль')}</b> <span className="muted">· {user.profile_missing.join() === 'ie_number' ? t('номер ИП для соглашения') : t('имя и фамилия, дата рождения, телефон, email')}</span></span>
          <ArrowRight size={16} color="var(--faint)" />
        </Link>
      )}
      {isLoading ? <Loading /> : error ? <ErrorBox error={error} /> : data && (
        <>
          <div className={`grid ${['deals', 'commission', 'objects', 'reposts'].filter(show).length > 3 ? 'g5' : 'g4'}`}>
            {show('deals') && <Stat blue label={t('Сделок за месяц')} value={num(data.deals_count)} icon={<Handshake size={18} />}
              sub={target ? <><span>{t('План {n}', { n: target })}</span><div className="mt"><Progress value={data.deals_count || 0} max={target} /></div></> : undefined} />}
            {show('commission') && <Stat label={t('Комиссия платформы')} value={money(data.platform_commission)} icon={<Coins size={18} color="var(--brand)" />} sub={t('за текущий месяц')} />}
            {show('objects') && <Stat label={t('Активных объектов')} value={num(data.active_objects)} icon={<Building2 size={18} color="var(--brand)" />} sub={t('в канале и базе')} />}
            {show('reposts') && <Stat label={t('Репостов')} value={num(data.reposts)} icon={<Repeat2 size={18} color="var(--brand)" />} sub={data.sla_overdue ? <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{t('Просрочено заявок:')} {data.sla_overdue}</span> : t('за месяц')} />}
            <Link to="/me" style={{ display: 'grid', color: 'inherit', textDecoration: 'none' }}>
              <Stat label={t('Личный кабинет')} value={user?.level ? `${user.level}%` : <ArrowRight size={28} />} icon={<CircleUser size={18} color="var(--brand)" />}
                sub={user?.level ? t('уровень · сделки, объекты') : t('сделки, объекты, статистика')} />
            </Link>
          </div>

          {data.stats && !metrics?.stats_off && <div className="section"><StatsBlock s={data.stats as Stats} staff={isStaff} /></div>}
          {data.stats_mine && !metrics?.stats_off && <div className="section"><StatsBlock s={data.stats_mine as Stats} staff={false} /></div>}

          <div className="split section">
            <div className="col gap-lg">
              <MyTasks />
              {isStaff && user?.works_as_agent && <MyTasks agent />}
              {show('funnel') && (
                <div className="grid g2">
                  <Card title={t('Объекты')}>
                    <FunnelRow order={PROPERTY_BOARD} labels={PROPERTY_STATUS} counts={data.funnel?.properties} link="/objects?tab=board" />
                  </Card>
                  <Card title={t('Заявки')}>
                    <FunnelRow order={LEAD_BOARD} labels={LEAD_STATUS} counts={data.funnel?.leads} link="/leads" />
                  </Card>
                </div>
              )}
            </div>
            <div className="col gap-lg">
              <Birthdays />
              {show('top_agents') && (
                <Card label={t('Лидеры')} title={t('Топ-5 агентов')} actions={<Link to="/team" className="label">{t('Все')}</Link>}>
                  {(data.top_agents || []).length === 0 ? <Empty /> : (data.top_agents || []).slice(0, 5).map((a, i) => {
                    const next = a.next_level_at ?? nextLevelAt(a.exclusive_deals);
                    return (
                      <div key={a.id} className="list-row">
                        <span className={`rank ${i === 0 ? 'top' : ''}`}>{i + 1}</span>
                        <Avatar name={a.name} src={a.photo_url} />
                        <div className="grow">
                          <div className="row row-between"><b>{a.name}</b><span className="badge">{a.level || 50}%</span></div>
                          <div className="muted" style={{ fontSize: 12 }}>{t('{n} эксклюзивов', { n: a.exclusive_deals })}{next ? ` · ${t('до {p}%: {n}', { p: a.level === 50 ? 70 : 90, n: next - a.exclusive_deals })}` : ''}</div>
                        </div>
                      </div>
                    );
                  })}
                </Card>
              )}
              {show('telegram_top') && (data.telegram_top || []).length > 0 && (
                <Card label="Telegram" title={t('Топ-10 постов')} actions={<Send size={16} color="var(--brand)" />}>
                  {(data.telegram_top || []).slice(0, 10).map((t, i) => (
                    <div key={i} className="list-row" style={{ padding: '7px 0' }}>
                      <span className="rank" style={{ width: 22, height: 22, fontSize: 11 }}>{i + 1}</span>
                      <span className="grow ellipsis" style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</span>
                      <span className="num muted" style={{ fontSize: 12, fontWeight: 700 }}>{num(t.value)}</span>
                    </div>
                  ))}
                </Card>
              )}
              {show('response_times') && rt && (
                <Card label={t('Скорость')} title={t('Время реакции, 30 дней')}>
                  <div className="grid g2">
                    <div><div className="label">{t('Оператор берёт')}</div><div className="stat-value" style={{ fontSize: 22 }}>{rt.operator_take_avg_min ?? '—'}<span className="muted" style={{ fontSize: 12 }}> {t('мин')}</span></div></div>
                    <div><div className="label">{t('Агент даёт время')}</div><div className="stat-value" style={{ fontSize: 22 }}>{rt.agent_slots_avg_min ?? '—'}<span className="muted" style={{ fontSize: 12 }}> {t('мин')}</span></div></div>
                  </div>
                </Card>
              )}
              <Card label="SLA" title={t('Сроки шагов')}>
                <div className="col gap-sm muted" style={{ fontSize: 13 }}>
                  <div className="row"><Clock size={14} />{t('Оператор берёт заявку: 5 мин')}</div>
                  <div className="row"><Clock size={14} />{t('Агент вводит время: 30 мин')}</div>
                  <div className="row"><Clock size={14} />{t('Время клиенту: 1 ч')}</div>
                  <div className="row"><Clock size={14} />{t('Проверка объекта: до 1 ч')}</div>
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </>
  );
}
