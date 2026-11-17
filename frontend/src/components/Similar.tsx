// «Похожие объекты» (Stanislav 11-17): one flat is never worked twice. For an ad or an object, every candidate across our
// base (the archive too), ss / myhome / livo / korter, Facebook / Telegram and the competitors, with why it looks the
// same; the agent says «Дубль» / «Не дубль» (backend services/similar.py).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { api } from '../api';
import type { PropertyStatus, SimilarItem } from '../api/types';
import { Badge, Button, ErrorBox, Loading } from './ui';
import { PhotoStrip, PropertyStatusBadge } from './domain';
import { errText, useToast } from './toast';
import { t } from '../lib/i18n';
import { bedroomsLabel, districtLabel, money } from '../lib/format';

/** subject: «l:<ad id>» / «p:<object id>». intro: the warning line above the list (the review step, the take check). */
export function SimilarList({ subject, intro, emptyText, onLinked }: { subject: string; intro?: string; emptyText?: string; onLinked?: (pid: number) => void }) {
  const [kind, id] = [subject.slice(0, 1), subject.slice(2)];
  const qk = ['similar', subject];
  const { data, isLoading, error } = useQuery({
    queryKey: qk,
    queryFn: () => (kind === 'p' ? api.properties.similar(Number(id)) : api.listings.similar(id)),
  });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const items = data?.items || [];
  if (!items.length) return emptyText ? <div className="muted" style={{ fontSize: 13 }}>{emptyText}</div> : null;
  return (
    <div className="col gap-sm">
      {intro && <div className="alert alert-warn" style={{ fontSize: 13 }}>{intro}</div>}
      {items.map((x) => <SimilarRow key={x.key} subject={subject} x={x} qk={qk} onLinked={onLinked} />)}
    </div>
  );
}

function SimilarRow({ subject, x, qk, onLinked }: { subject: string; x: SimilarItem; qk: unknown[]; onLinked?: (pid: number) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const loc = useLocation();
  const decide = useMutation({
    mutationFn: (same: boolean) => api.similar.decide(subject, x.key, same),
    onSuccess: (r, same) => {
      qc.invalidateQueries({ queryKey: qk });
      qc.invalidateQueries({ queryKey: ['listings'] });
      qc.invalidateQueries({ queryKey: ['property'] });
      if (r.linked_to) { toast(t('Объявление привязано к объекту #{id}', { id: r.linked_to })); onLinked?.(r.linked_to); }
      else toast(same ? t('Отмечено: дубль') : t('Отмечено: другой объект'));
    },
    onError: (e) => toast(errText(e), true),
  });
  const obj = x.kind === 'object';
  const title = obj ? t('Объект #{id}', { id: x.property_id ?? '' }) : x.where;
  const params = [districtLabel(x.district), bedroomsLabel(x.bedrooms), x.area ? `${x.area} ${t('м²')}` : null,
    x.floor != null ? t('этаж {n}', { n: x.floor }) : null, x.price_usd ? money(x.price_usd, 'USD') : null].filter(Boolean).join(' · ');
  const objLink = obj && x.can_open ? `${loc.pathname.startsWith('/m/') ? '/m/properties' : '/objects'}/${x.property_id}` : null;
  return (
    <div className="card" style={{ padding: 12, borderColor: x.level === 'same' ? 'var(--red, #d33)' : undefined }}>
      <div className="col gap-sm">
        <div className="row row-wrap gap-sm" style={{ alignItems: 'center' }}>
          <Badge tone={x.level === 'same' ? 'red' : 'warn'}>{x.level === 'same' ? t('почти точно тот же') : t('похож')}</Badge>
          <strong>{title}</strong>
          {obj && x.status && <PropertyStatusBadge status={x.status as PropertyStatus} />}
          {!obj && <Badge tone={x.competitor ? 'redsoft' : 'grey'}>{x.competitor ? t('конкурент') : t('объявление')}</Badge>}
          {obj && x.is_exclusive && <Badge tone="solid">{t('эксклюзив')}</Badge>}
          {x.decided === 'same' && <Badge tone="red">{t('отмечен дублем')}</Badge>}
        </div>
        <div style={{ fontSize: 14 }}>{x.address || t('Адрес не указан')}</div>
        {params && <div className="muted" style={{ fontSize: 13 }}>{params}</div>}
        {obj && <div className="faint" style={{ fontSize: 12 }}>{x.agent ? t('Ведёт: {name}', { name: x.agent }) : t('Без агента')}</div>}
        <div style={{ fontSize: 13 }}><span className="label">{t('Почему: ')}</span>{x.reasons.join(' · ')}</div>
        {obj && !x.can_open && !x.photos.length
          ? <div className="faint" style={{ fontSize: 12 }}>{t('Фото объекта видит его агент и оператор')}</div>
          : <PhotoStrip photos={x.photos} />}
        <div className="row row-wrap gap-sm">
          {objLink && <Link className="btn btn-secondary btn-sm" to={objLink}><ExternalLink size={14} />{t('Открыть объект')}</Link>}
          {x.url && <a className="btn btn-secondary btn-sm" href={x.url} target="_blank" rel="noreferrer"><ExternalLink size={14} />{obj ? t('Пост в канале') : t('Открыть источник')}</a>}
          {x.decided !== 'same' && (
            <Button size="sm" loading={decide.isPending && decide.variables === true} onClick={() => decide.mutate(true)}>
              {subject.startsWith('l:') && obj ? t('Дубль: это он') : t('Дубль')}
            </Button>
          )}
          <Button size="sm" variant="secondary" loading={decide.isPending && decide.variables === false} onClick={() => decide.mutate(false)}>{t('Не дубль')}</Button>
        </div>
      </div>
    </div>
  );
}

/** «Беру в работу» answered possible_duplicate: the objects of our base this ad may be. «Дубль: это он» links the ad to
 * that object (nothing new is made); «Это другой объект — беру» takes it anyway, those objects are noted as different. */
export function TakeCheck({ listingId, items, taking, onTake, onClose }: { listingId: string; items: SimilarItem[]; taking: boolean; onTake: () => void; onClose: () => void }) {
  return (
    <div className="col gap-lg">
      <div className="alert alert-warn">{t('Похоже, эта квартира уже есть в нашей базе. Проверьте, чтобы не работать с одним объектом дважды: если это он — нажмите «Дубль: это он».')}</div>
      <div className="col gap-sm">{items.map((x) => <SimilarRow key={x.key} subject={`l:${listingId}`} x={x} qk={['similar', `l:${listingId}`]} onLinked={onClose} />)}</div>
      <div className="modal-actions">
        <Button block loading={taking} onClick={onTake}>{t('Это другой объект — беру в работу')}</Button>
        <Button block variant="secondary" onClick={onClose}>{t('Отмена')}</Button>
      </div>
    </div>
  );
}
