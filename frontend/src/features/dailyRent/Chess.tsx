// «Посуточная аренда» → «Шахматка»: apartments × days of a month. Our stays, platform bookings from the iCal feeds and
// manual closures; double bookings in red, platform bookings with no stay entered in «Требует внимания».
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Lock } from 'lucide-react';
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, Loading, Modal, PageHead, Switch } from '../../components/ui';
import { errText, useToast } from '../../components/toast';
import { MonthPicker } from '../../pages/StatsCharts';
import { BookingModal, useDrInvalidate } from './Booking';
import { useDrData } from './DailyRent';
import { addMonths, dm, dr, ymLabel, ymNow, type DrApartment, type Interval, type Platform } from './api';

const ORIGIN: Record<string, string> = { airbnb: 'Airbnb', booking: 'Booking', other: 'Другая площадка', manual: 'Закрыто вручную' };
const WD = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const toPlatform = (o: string): Platform => (o === 'airbnb' ? 'Airbnb' : o === 'booking' ? 'Booking' : 'Другое');
const addDay = (d: string, n: number) => { const x = new Date(d + 'T12:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const label = (x: Interval) => (x.kind === 'stay' ? `${x.guest || 'Гость'} · ${x.platform}` : `${ORIGIN[x.origin] || x.origin}${x.summary ? ` · ${x.summary}` : ''}`);

export function ChessPage() {
  const [month, setMonth] = useState(ymNow());
  const start = `${month}-01`, end = `${addMonths(month, 1)}-01`;
  const data = useDrData();
  const q = useQuery({ queryKey: ['dr', 'calendar', month], queryFn: () => dr.calendar(start, end) });
  const [stay, setStay] = useState<number | null>(null);
  const [create, setCreate] = useState<{ apt: DrApartment; start: string; end?: string; platform?: Platform } | null>(null);
  const [pick, setPick] = useState<{ apt: DrApartment; day: string; item?: Interval } | null>(null);
  const [all, setAll] = useState(false);
  const days = useMemo(() => { const out: string[] = []; for (let d = start; d < end; d = addDay(d, 1)) out.push(d); return out; }, [start, end]);
  if (q.isLoading || data.isLoading) return <Loading />;
  if (!q.data || !data.data) return <ErrorBox error={q.error || data.error} />;
  const apts = data.data.apartments.filter((a) => all || a.active);
  const names = new Map(data.data.apartments.map((a) => [a.id, a.name]));
  const bad = new Set<string>();
  for (const c of q.data.conflicts) for (const x of [c.a, c.b]) bad.add(`${x.kind}:${x.id}`);
  const items = q.data.items.filter((x) => !x.echo);
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tbilisi' });
  const open = (apt: DrApartment, day: string, item?: Interval) => {
    if (item?.kind === 'stay') setStay(item.id);
    else setPick({ apt, day, item });
  };
  return (
    <>
      <PageHead label="Посуточная аренда" title="Шахматка" actions={<MonthPicker value={month} max={addMonths(ymNow(), 12)} onChange={setMonth} />} />
      {(q.data.conflicts.length > 0 || q.data.unaccounted.length > 0) && (
        <Card label="Требует внимания" title={<span className="row gap-sm"><AlertTriangle size={18} />Пересечения и брони без проживания</span>}>
          <div className="col gap-sm">
            {q.data.conflicts.map((c) => (
              <div key={c.key} className="row gap-sm row-wrap"><Badge tone="red">Двойная занятость</Badge>
                <b>{names.get(c.apartment_id)}</b><span>{dm(c.start)} — {dm(c.end)}: {label(c.a)} и {label(c.b)}</span></div>
            ))}
            {q.data.unaccounted.map((b) => {
              const a = data.data!.apartments.find((x) => x.id === b.apartment_id);
              return (
                <div key={b.id} className="row gap-sm row-wrap"><Badge tone="warn">Бронь {ORIGIN[b.origin]}</Badge>
                  <b>{names.get(b.apartment_id)}</b><span>{dm(b.start)} — {dm(b.end)}: проживание ещё не внесено</span>
                  {a && <Button size="sm" variant="secondary" onClick={() => setCreate({ apt: a, start: b.start, end: b.end, platform: toPlatform(b.origin) })}>Внести деньги</Button>}
                </div>
              );
            })}
          </div>
        </Card>
      )}
      <Card pad={false} title={ymLabel(month)} actions={<Switch checked={all} onChange={setAll} label="Неактивные" />}>
        {apts.length === 0 ? <Empty text="Квартир нет" /> : (
          <div className="table-wrap">
            <table className="dr-chess">
              <thead><tr><th className="dr-chess-apt" />{days.map((d) => {
                const wd = new Date(d + 'T12:00:00').getDay();
                return <th key={d} className={`${d === today ? 'today' : ''} ${wd === 0 || wd === 6 ? 'we' : ''}`}>{Number(d.slice(8))}<small>{WD[wd]}</small></th>;
              })}</tr></thead>
              <tbody>{apts.map((a) => {
                const mine = items.filter((x) => x.apartment_id === a.id);
                return (
                  <tr key={a.id}>
                    <th className="dr-chess-apt" title={a.address || ''}>{a.name}</th>
                    {days.map((d) => {
                      const here = mine.filter((x) => x.start <= d && d < x.end);
                      const x = here.find((i) => i.kind === 'stay') || here[0];
                      const cls = !x ? '' : `o-${x.kind === 'stay' ? 'stay-' + x.origin : x.origin}${x.reserved === false ? ' na' : ''}${here.some((i) => bad.has(`${i.kind}:${i.id}`)) ? ' bad' : ''}`;
                      const first = x && (x.start === d || d === start);
                      return (
                        <td key={d} className={cls} title={here.map(label).join('\n') || 'Свободно'} onClick={() => open(a, d, x)}>
                          {first && <span>{x.kind === 'block' && x.origin === 'manual' ? <Lock size={10} /> : null}{x.kind === 'stay' ? x.guest || '·' : ORIGIN[x.origin]?.slice(0, 3)}</span>}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
        <div className="dr-chess-legend">
          <span className="o-stay-airbnb">Проживание Airbnb</span><span className="o-stay-booking">Проживание Booking</span><span className="o-stay-other">Другое</span>
          <span className="o-airbnb">Бронь Airbnb (iCal)</span><span className="o-booking">Бронь Booking (iCal)</span><span className="o-manual">Закрыто вручную</span><span className="bad">Пересечение</span>
        </div>
      </Card>
      {pick && <PickModal pick={pick} onClose={() => setPick(null)} onNew={(p) => { setPick(null); setCreate(p); }} />}
      <BookingModal open={stay} onClose={() => setStay(null)} />
      {create && <BookingModal open="new" apt={create.apt} prefill={{ check_in: create.start, check_out: create.end, platform: create.platform }} onClose={() => setCreate(null)} />}
    </>
  );
}

function PickModal({ pick, onClose, onNew }: { pick: { apt: DrApartment; day: string; item?: Interval }; onClose: () => void; onNew: (p: { apt: DrApartment; start: string; end?: string; platform?: Platform }) => void }) {
  const toast = useToast();
  const refresh = useDrInvalidate();
  const [endD, setEnd] = useState(addDay(pick.day, 1));
  const [reason, setReason] = useState('');
  const { apt, day, item } = pick;
  const block = (force = false) => dr.createBlock({ apartment_id: apt.id, start: day, end: endD, reason, force })
    .then(() => { refresh(); toast('Даты закрыты'); onClose(); }, (e) => toast(errText(e), true));
  return (
    <Modal open onClose={onClose} title={`${apt.name} · ${dm(day)}`}>
      {item ? (
        <div className="col gap">
          <p><b>{label(item)}</b><br /><span className="muted">{dm(item.start)} — {dm(item.end)}</span></p>
          {item.origin === 'manual'
            ? <Button variant="secondary" onClick={() => dr.cancelBlock(item.id).then(() => { refresh(); toast('Блокировка снята'); onClose(); }, (e) => toast(errText(e), true))}>Снять блокировку</Button>
            : <Button onClick={() => onNew({ apt, start: item.start, end: item.end, platform: toPlatform(item.origin) })}>Внести проживание по этой брони</Button>}
        </div>
      ) : (
        <div className="col gap">
          <Button onClick={() => onNew({ apt, start: day })}>Новое проживание с {dm(day)}</Button>
          <div className="form-grid">
            <Field label="Закрыть даты: по (выезд)"><Input type="date" value={endD} min={addDay(day, 1)} onChange={(e) => setEnd(e.target.value)} /></Field>
            <Field label="Причина"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="ремонт, свои гости…" /></Field>
          </div>
          <Button variant="secondary" disabled={endD <= day} onClick={() => block()}><Lock size={15} />Закрыть даты</Button>
        </div>
      )}
    </Modal>
  );
}
