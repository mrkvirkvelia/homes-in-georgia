// «Статистика» (Stanislav 11-13, for David): the old workbook sheet «TBILISI ANALYSIS RENT AND SALE» rebuilt live from
// the CRM — objects / clients / rent-outs / cash-in by month and by agent, client sources, prices by district × bedrooms.
// Data: GET /api/analytics/stats?month=YYYY-MM (superadmins only). Block ↔ sheet mapping: docs/STATS-BLOCKS.md.
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { http } from '../api/client';
import { Card, Empty, ErrorBox, Loading, PageHead, Seg, Stat } from '../components/ui';
import { Bars, VBars } from '../features/deals/Analytics';
import { money, num } from '../lib/format';

type Trend = { month: string; objects: number; clients: number; budget_sum: number; rentouts: number; commission: number; platform: number; agents: number };
type Agent = { id: number | null; name: string; objects: number; ppm: number | null; clients: number; rentouts: number; commission: number;
  agent_amount: number; platform: number; share: number | null; obj_conv: number | null; client_conv: number | null; quality: number | null };
type Cell = { count: number; median: number; ppm: number | null };
type PriceRow = { district: string; count: number; cells: Record<string, Cell> };
export type MonthStats = {
  month: string;
  summary: { objects: number; objects_sale: number; objects_avg_price: number; objects_avg_ppm: number; clients: number; clients_avg_budget: number;
    clients_with_budget: number; budget_sum: number; rentouts: number; commission: number; platform: number; agents: number;
    by_type: Record<string, { count: number; commission: number; avg_price: number }>; mom: Record<string, number | null> };
  trend: Trend[]; agents: Agent[]; sources: { source: string; count: number }[]; prices: { objects: PriceRow[]; market: PriceRow[] };
};

const MON = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const short = (k: string) => { const [y, m] = k.split('-'); return `${MON[Number(m) - 1]} ${y.slice(2)}`; };
const thisMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };
const k$ = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v}`);
const pct = (v: number | null | undefined) => (v == null ? '—' : `${v}%`);
const mom = (v: number | null | undefined) => (v == null ? 'нет прошлого месяца' : `${v > 0 ? '+' : ''}${v}% к прошлому`);
const BEDS: [string, string][] = [['0', 'Студия'], ['1', '1'], ['2', '2'], ['3', '3'], ['4', '4+']];
const R = { textAlign: 'right' } as const;

type Metric = 'objects' | 'clients' | 'rentouts' | 'commission';
const METRICS: { value: Metric; label: string }[] = [{ value: 'rentouts', label: 'Сдано' }, { value: 'commission', label: 'Комиссия' },
  { value: 'clients', label: 'Клиенты' }, { value: 'objects', label: 'Объекты' }];

export function StatsPage() {
  const [month, setMonth] = useState(thisMonth());
  const [metric, setMetric] = useState<Metric>('rentouts');
  const [src, setSrc] = useState<'objects' | 'market'>('objects');
  const q = useQuery({ queryKey: ['stats', month], queryFn: () => http.get<MonthStats>('/analytics/stats', { month }) });
  const d = q.data;
  const s = d?.summary;
  const rent = s?.by_type.rent, sale = s?.by_type.sale;
  const prices = d?.prices[src] || [];
  return (
    <div className="col gap-lg">
      <PageHead label="Для руководителя" title="Статистика"
        actions={<input className="input" type="month" aria-label="Месяц" value={month} max={thisMonth()} onChange={(e) => e.target.value && setMonth(e.target.value)} style={{ width: 170 }} />} />
      {q.isLoading ? <Loading /> : q.error ? <ErrorBox error={q.error} /> : !d || !s ? <Empty /> : (<>
        <div className="grid g4">
          <Stat blue label="Сдано квартир" value={num(s.rentouts)} sub={mom(s.mom.rentouts)} />
          <Stat label="Комиссия (cash-in)" value={money(s.commission)} sub={mom(s.mom.commission)} />
          <Stat label="Платформе" value={money(s.platform)} sub={`агентам ${money(s.agents)}`} />
          <Stat label="Продажи" value={num(sale?.count || 0)} sub={sale ? `комиссия ${money(sale.commission)}` : 'сделок продажи нет'} />
          <Stat label="Новых объектов" value={num(s.objects)} sub={mom(s.mom.objects)} />
          <Stat label="Ср. цена объекта" value={s.objects_avg_price ? money(s.objects_avg_price) : '—'} sub={s.objects_avg_ppm ? `$${s.objects_avg_ppm} за м²` : 'нет площади'} />
          <Stat label="Клиентов" value={num(s.clients)} sub={mom(s.mom.clients)} />
          <Stat label="Ср. бюджет клиента" value={s.clients_avg_budget ? money(s.clients_avg_budget) : '—'} sub={`сумма ${money(s.budget_sum)} · ${s.clients_with_budget} с бюджетом`} />
        </div>
        {rent && <div className="muted" style={{ fontSize: 12, marginTop: -8 }}>Аренда: {rent.count} сделок, средняя цена {money(rent.avg_price)}.</div>}

        <Card label="По месяцам" title="Динамика за 12 месяцев" actions={<Seg value={metric} onChange={setMetric} options={METRICS} />}>
          <div className="table-wrap"><div style={{ minWidth: 560 }}>{/* 12 bars don't fit 375 px: scroll inside the card */}
            <VBars rows={d.trend.map((t) => ({ k: short(t.month), v: t[metric] }))} fmt={metric === 'commission' ? k$ : num} />
          </div></div>
        </Card>
        <Card label="По месяцам" title="Таблица по месяцам" pad={false}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Месяц</th><th style={R}>Объекты</th><th style={R}>Клиенты</th><th style={R}>Бюджеты $</th><th style={R}>Сдано</th><th style={R}>Комиссия</th><th style={R}>Платформа</th><th style={R}>Агентам</th></tr></thead>
              <tbody>{[...d.trend].reverse().map((t) => (
                <tr key={t.month}><td className="nowrap"><b>{short(t.month)}</b></td><td className="num" style={R}>{num(t.objects)}</td><td className="num" style={R}>{num(t.clients)}</td>
                  <td className="num" style={R}>{money(t.budget_sum)}</td><td className="num" style={R}>{num(t.rentouts)}</td><td className="num" style={R}>{money(t.commission)}</td>
                  <td className="num" style={R}>{money(t.platform)}</td><td className="num" style={R}>{money(t.agents)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </Card>

        <Card label="За месяц" title="Агенты: объекты, клиенты, сдачи, cash-in" pad={false}>
          {d.agents.length === 0 ? <Empty text="Нет данных за месяц" /> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Агент</th><th style={R}>Объекты</th><th style={R}>$/м²</th><th style={R}>Клиенты</th><th style={R}>Сдано</th><th style={R}>Cash-in</th>
                  <th style={R}>Агенту</th><th style={R}>%</th><th style={R}>Платформе</th><th style={R} title="Сдано / объекты">Объекты→сдано</th><th style={R} title="Сдано / клиенты">Клиенты→сдано</th><th style={R} title="Среднее двух конверсий, как Quality в таблице">Качество</th></tr></thead>
                <tbody>{d.agents.map((a) => (
                  <tr key={a.id ?? 'none'}><td className="nowrap"><b>{a.name}</b></td><td className="num" style={R}>{num(a.objects)}</td><td className="num" style={R}>{a.ppm ?? '—'}</td>
                    <td className="num" style={R}>{num(a.clients)}</td><td className="num" style={R}>{num(a.rentouts)}</td><td className="num" style={R}>{money(a.commission)}</td>
                    <td className="num" style={R}>{money(a.agent_amount)}</td><td className="num" style={R}>{pct(a.share)}</td><td className="num" style={R}>{money(a.platform)}</td>
                    <td className="num" style={R}>{pct(a.obj_conv)}</td><td className="num" style={R}>{pct(a.client_conv)}</td><td className="num" style={R}><b>{pct(a.quality)}</b></td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="grid g2">
          <Card label="За месяц" title="Откуда пришли клиенты">
            <Bars rows={d.sources.map((x) => ({ k: x.source, v: x.count, sub: `${Math.round((x.count / Math.max(1, d.sources.reduce((t, y) => t + y.count, 0))) * 100)}%` }))} />
          </Card>
          <Card label="За месяц" title="Cash-in по агентам">
            <Bars rows={d.agents.filter((a) => a.commission > 0).map((a) => ({ k: a.name, v: a.commission, sub: `${a.rentouts} сд.` }))} fmt={money} />
          </Card>
        </div>

        <Card label="За месяц" title="Цены аренды: район × спальни (медиана)" pad={false}
          actions={<Seg value={src} onChange={setSrc} options={[{ value: 'objects', label: 'Наши объекты' }, { value: 'market', label: 'Рынок (парсер)' }]} />}>
          {prices.length === 0 ? <Empty text={src === 'market' ? 'Нет данных в CRM: парсер собирает объявления с 10.11.2026' : 'Нет объектов за месяц'} /> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Район</th><th style={R}>Всего</th>{BEDS.map(([k, l]) => <th key={k} style={R}>{l}</th>)}</tr></thead>
                <tbody>{prices.map((p) => (
                  <tr key={p.district}><td className="nowrap"><b>{p.district}</b></td><td className="num" style={R}>{p.count}</td>
                    {BEDS.map(([k]) => { const c = p.cells[k]; return (
                      <td key={k} className="num nowrap" style={R} title={c ? `${c.count} шт.${c.ppm ? ` · $${c.ppm}/м²` : ''}` : undefined}>
                        {c ? <>{money(c.median)} <span className="muted" style={{ fontSize: 11 }}>· {c.count}</span></> : <span className="muted">—</span>}</td>); })}
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
        <div className="muted" style={{ fontSize: 12 }}>
          Объекты — добавленные в CRM за месяц, клиенты — заявки за месяц, сдано и cash-in — сделки (подтверждённые и ожидающие) с этим месяцем.
          Бюджет клиента берётся из запроса заявки («$700»). Данных о рынке продаж в CRM нет.
        </div>
      </>)}
    </div>
  );
}
