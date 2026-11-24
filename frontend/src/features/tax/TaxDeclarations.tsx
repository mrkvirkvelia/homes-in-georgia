// «Декларации RS.ge» (Irakli 11-24, backend services/tax.py): an agent with an ИП types the month's turnover from his
// bank statement, sees the 1 % tax, files on rs.ge himself and marks «Подал». Staff see the team's state per month.
import { Fragment, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Receipt } from 'lucide-react';
import { api } from '../../api';
import type { TaxDecl, TaxStatus } from '../../api/types';
import { errText, useToast } from '../../components/toast';
import { Avatar, Badge, Button, Card, Checkbox, Empty, ErrorBox, Field, Input, Loading, Stat } from '../../components/ui';
import { fmtDate, monthLabel } from '../../lib/format';
import { t } from '../../lib/i18n';

/** «2026-10» → «октябрь 2026» (format.monthLabel takes «10/2026») */
export const periodLabel = (p: string) => { const [y, m] = p.split('-'); return monthLabel(`${Number(m)}/${y}`); };
export const gel = (v?: number | null) => (v === null || v === undefined ? '—'
  : `${Number(v).toLocaleString('ru-RU', Number.isInteger(Number(v)) ? {} : { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace(/,/g, '.').replace(/ /g, ' ')} ₾`);

const STATUS: Record<TaxStatus, { label: string; tone: 'ok' | 'warn' | 'grey' }> = {
  filed: { label: t('Подана'), tone: 'ok' },
  entered: { label: t('Сумма внесена'), tone: 'warn' },
  missing: { label: t('Не подана'), tone: 'grey' },
};

export function TaxBadge({ d }: { d: Pick<TaxDecl, 'status' | 'overdue'> }) {
  if (d.overdue) return <Badge tone="red">{t('Просрочена')}</Badge>;
  const s = STATUS[d.status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

function when(d: TaxDecl) {
  if (d.status === 'filed') return t('подана {d}', { d: fmtDate(d.filed_at) });
  if (d.days_left > 0) return t('до {d}, осталось {n} дн.', { d: fmtDate(d.deadline), n: d.days_left });
  if (d.days_left === 0) return t('сегодня последний день');
  return t('срок был {d}', { d: fmtDate(d.deadline) });
}

/** The form for one month: turnover (GEL), «Подал на rs.ge», note. */
function DeclForm({ d, rsUrl, onDone }: { d: TaxDecl; rsUrl: string; onDone?: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [sum, setSum] = useState(d.turnover === null ? '' : String(d.turnover));
  const [filed, setFiled] = useState(d.status === 'filed');
  const [note, setNote] = useState(d.note || '');
  const amount = Number(sum.replace(',', '.').replace(/\s/g, ''));
  const valid = sum.trim() !== '' && Number.isFinite(amount) && amount >= 0;
  const save = useMutation({
    mutationFn: () => api.tax.save(d.period, { turnover: amount, filed, note: note.trim() || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tax'] }); toast(filed ? t('Отмечено: декларация подана') : t('Сумма сохранена')); onDone?.(); },
    onError: (e) => toast(errText(e), true),
  });
  return (
    <div className="col gap">
      <div className="form-grid">
        <Field label={t('Поступления за месяц, ₾')} hint={t('Сумма всех поступлений на счёт ИП по банковской выписке, в лари. Нет поступлений: 0')}>
          <Input inputMode="decimal" value={sum} onChange={(e) => setSum(e.target.value)} placeholder="0" />
        </Field>
        <Field label={t('Налог 1%')}>
          <div className="stat-value" style={{ marginTop: 4 }}>{valid ? gel(Math.round(amount) / 100) : '—'}</div>
        </Field>
        <Field label={t('Комментарий')}><Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder={t('необязательно')} /></Field>
      </div>
      <Checkbox checked={filed} onChange={setFiled} disabled={!valid}>{t('Я подал декларацию на rs.ge')}</Checkbox>
      <div className="row gap-sm" style={{ flexWrap: 'wrap' }}>
        <Button disabled={!valid} loading={save.isPending} onClick={() => save.mutate()}>{t('Сохранить')}</Button>
        <a className="btn btn-ghost" href={rsUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} />{t('Открыть rs.ge')}</a>
      </div>
    </div>
  );
}

const HOWTO = [
  t('Откройте выписку по счёту ИП за прошлый месяц и сложите все поступления в лари.'),
  t('Внесите сумму здесь: CRM покажет налог 1%.'),
  t('Войдите на eservices.rs.ge (пароль и SMS-код) → Декларации → декларация лица со статусом малого бизнеса, период прошлого месяца.'),
  t('Впишите ту же сумму в поле «облагаемый оборот», отправьте и оплатите налог до 15-го.'),
  t('Вернитесь сюда и отметьте «Я подал декларацию».'),
];

/** The agent's own declarations (userId: staff looking at an employee's, read-only). */
export function MyTax({ userId }: { userId?: number }) {
  const { data, isLoading, error } = useQuery({ queryKey: ['tax', 'me', userId], queryFn: () => api.tax.mine(userId) });
  const [edit, setEdit] = useState<string | null>(null);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;
  const ro = !!userId;
  const cur = data.current;
  if (!data.has_ie) {
    return <Empty icon={<Receipt size={28} />} text={ro ? t('У сотрудника не указан номер ИП') : t('Укажите номер ИП (ი/მ) в профиле, чтобы вести декларации')} />;
  }
  return (
    <div className="col gap-lg">
      <Card label={t('Декларация RS.ge')} title={periodLabel(cur.period)} actions={<TaxBadge d={cur} />}>
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>{when(cur)}</div>
        {ro ? (
          <div className="grid g2">
            <Stat label={t('Поступления')} value={gel(cur.turnover)} />
            <Stat label={t('Налог 1%')} value={gel(cur.tax)} />
          </div>
        ) : <DeclForm key={`${cur.period}:${cur.updated_at}`} d={cur} rsUrl={data.rs_url} />}
      </Card>

      {!ro && (
        <Card label={t('Как подать')} title={t('Пять шагов')}>
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.6 }}>{HOWTO.map((s) => <li key={s}>{s}</li>)}</ol>
          <div className="faint mt" style={{ fontSize: 12 }}>{t('CRM ничего не отправляет на rs.ge сама: декларацию подаёте вы, здесь только учёт и напоминания в Telegram 1, 10 и 14 числа.')}</div>
        </Card>
      )}

      <div className="card table-wrap">
        <table className="table">
          <thead><tr><th>{t('Месяц')}</th><th>{t('Поступления')}</th><th>{t('Налог')}</th><th>{t('Статус')}</th>{!ro && <th />}</tr></thead>
          <tbody>
            {data.history.slice(1).map((d) => (
              <Fragment key={d.period}>
                <tr>
                  <td className="nowrap">{periodLabel(d.period)}</td>
                  <td className="num">{gel(d.turnover)}</td>
                  <td className="num">{gel(d.tax)}</td>
                  <td><TaxBadge d={d} /></td>
                  {!ro && <td style={{ textAlign: 'right' }}><Button size="sm" variant="ghost" onClick={() => setEdit(edit === d.period ? null : d.period)}>{edit === d.period ? t('Свернуть') : t('Изменить')}</Button></td>}
                </tr>
                {edit === d.period && (
                  <tr><td colSpan={5}><DeclForm d={d} rsUrl={data.rs_url} onDone={() => setEdit(null)} /></td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const lastPeriods = (n = 12) => {
  const out: string[] = [];
  const d = new Date();
  d.setDate(1);
  for (let i = 0; i < n; i++) { d.setMonth(d.getMonth() - 1); out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); }
  return out;
};

/** Staff: who filed the month's declaration. */
export function TeamTax({ onOpen }: { onOpen?: (userId: number) => void }) {
  const periods = lastPeriods();
  const [period, setPeriod] = useState(periods[0]);
  const { data, isLoading, error } = useQuery({ queryKey: ['tax', 'overview', period], queryFn: () => api.tax.overview(period) });
  return (
    <Card label={t('Команда')} title={t('Декларации RS.ge')} actions={
      <select className="select" style={{ width: 'auto' }} aria-label={t('Месяц')} value={period} onChange={(e) => setPeriod(e.target.value)}>
        {periods.map((p) => <option key={p} value={p}>{periodLabel(p)}</option>)}
      </select>}>
      {isLoading ? <Loading /> : error || !data ? <ErrorBox error={error} /> : (
        <div className="col gap">
          <div className="grid g4">
            <Stat label={t('С ИП')} value={data.totals.people} />
            <Stat label={t('Подали')} value={data.totals.filed} />
            <Stat label={t('Внесли сумму')} value={data.totals.entered} />
            <Stat label={t('Не начали')} value={data.totals.missing} sub={t('до {d}', { d: fmtDate(data.deadline) })} />
          </div>
          {data.rows.map((r) => (
            <div key={r.user.id} className="list-row" style={{ cursor: onOpen ? 'pointer' : undefined }} onClick={() => onOpen?.(r.user.id)}>
              <Avatar name={r.user.name} src={r.user.photo_url} />
              <span className="grow"><b>{r.user.name}</b>{r.has_ie && r.turnover !== null && <div className="muted" style={{ fontSize: 12 }}>{gel(r.turnover)} · {t('налог')} {gel(r.tax)}</div>}</span>
              {r.has_ie ? <TaxBadge d={r} /> : <Badge tone="grey">{t('нет ИП')}</Badge>}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
