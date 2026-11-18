// An owner's phones (David + Irakli 11-18): any number of them, each with an optional note («сестра», «WhatsApp»),
// any country. The first is the main one (backend owners.phone); the rest live in owners.phones.
import { Plus, X } from 'lucide-react';
import type { PhoneRow } from '../api/types';
import { Button, Input } from './ui';
import { CopyPhone } from './domain';
import { formatPhone, phoneInput } from '../lib/format';
import { t } from '../lib/i18n';

/** The rows to edit: the owner's list, else his single phone, else one empty row. */
export const phoneRows = (o?: { phone?: string | null; phones?: PhoneRow[] | null } | null): PhoneRow[] =>
  o?.phones?.length ? o.phones.map((r) => ({ phone: formatPhone(r.phone), note: r.note || '' }))
    : [{ phone: o?.phone ? formatPhone(o.phone) : '', note: '' }];

/** What to send: rows with a number (a bare «+995 » dropped), notes trimmed. */
export const cleanPhones = (rows: PhoneRow[]): PhoneRow[] =>
  rows.filter((r) => r.phone.replace(/\D/g, '').replace(/^995$/, '')).map((r) => ({ phone: r.phone.trim(), note: r.note?.trim() || null }));

const digits = (s?: string | null) => (s || '').replace(/\D/g, '').replace(/^995/, '').replace(/^0/, '');
/** Same numbers, notes and order (the «changed?» check of a form). */
export const samePhones = (a: PhoneRow[], b: PhoneRow[]) =>
  JSON.stringify(cleanPhones(a).map((r) => [digits(r.phone), r.note || ''])) === JSON.stringify(cleanPhones(b).map((r) => [digits(r.phone), r.note || '']));

export function PhonesField({ value, onChange, label = t('Телефон') }: { value: PhoneRow[]; onChange: (rows: PhoneRow[]) => void; label?: string }) {
  const set = (i: number, patch: Partial<PhoneRow>) => onChange(value.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="field span2">
      <span className="label">{label}</span>
      <div className="col gap-sm">
        {value.map((r, i) => (
          <div key={i} className="phones-row">
            <Input type="tel" inputMode="tel" value={r.phone} aria-label={i ? t('Ещё номер') : label}
              placeholder={i ? '+995 5__ ___ ___ / +7 …' : '+995 5__ ___ ___'} onChange={(e) => set(i, { phone: phoneInput(e) })} />
            <Input value={r.note || ''} maxLength={100} aria-label={t('Заметка к номеру')}
              placeholder={i ? t('Чей номер: сестра, WhatsApp…') : t('Основной · заметка')} onChange={(e) => set(i, { note: e.target.value })} />
            {value.length > 1 && (
              <Button variant="ghost" size="sm" aria-label={t('Убрать номер')} title={t('Убрать номер')}
                onClick={() => onChange(value.filter((_, j) => j !== i))}><X size={16} /></Button>
            )}
          </div>
        ))}
      </div>
      <div><Button variant="ghost" size="sm" onClick={() => onChange([...value, { phone: '', note: '' }])}><Plus size={14} />{t('Ещё номер')}</Button></div>
    </div>
  );
}

/** The owner's other numbers under his main one (the main is shown by the caller). */
export function MorePhones({ phones }: { phones?: PhoneRow[] | null }) {
  const rest = (phones || []).slice(1);
  if (!rest.length) return null;
  return (
    <div className="col gap-sm" style={{ marginTop: 4 }}>
      {rest.map((r) => (
        <span key={r.phone} className="row gap-sm row-wrap" style={{ display: 'inline-flex' }}>
          <a href={`tel:${r.phone.replace(/[^+\d]/g, '')}`} style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>{formatPhone(r.phone)}</a>
          {r.note && <span className="muted" style={{ fontSize: 12 }}>{r.note}</span>}
          <CopyPhone phone={r.phone} />
        </span>
      ))}
    </div>
  );
}
