// /ndas (staff; no menu item — Управление → Пользователи → «Соглашение (NDA)»): the agreement (edition 1.1) for new agents (backend services/nda.py, docs/NDA.md). David draws the company's signature once;
// staff fill in the agent and send him the personal link /nda/<token>; he confirms himself with Telegram and signs.
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Download, Eye, FileText, Plus, RotateCcw, Save, Send, Share2, ShieldCheck, Trash2, XCircle } from 'lucide-react';
import { fetchBlob, http, itemsOf } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { errText, useToast } from '../components/toast';
import { Badge, Button, Card, Empty, Field, Input, Loading, Modal, PageHead, Select, Tabs, Textarea } from '../components/ui';
import { t } from '../lib/i18n';
import { SignaturePad, signaturePng } from '../components/SignaturePad';
import { fmtDate, fmtDateTime, phoneInput } from '../lib/format';

interface Nda {
  id: number; status: 'sent' | 'signed' | 'cancelled'; status_label: string; lang: 'KA' | 'KA-RU' | 'KA-EN';
  full_name: string; personal_id: string; phone: string | null; telegram: string | null; role: string | null;
  path: string | null; created_at: string; created_by: { id: number; name: string } | null; signed_at: string | null;
  tg_username: string | null; has_pdf: boolean; number: string;
  details: { ie?: string; ie_amended?: { ie: string; at: string } };
}
interface CompanySig { signature: string | null; at: string | null; by_name: string | null; edition?: string }
const LANGS = [{ value: 'KA-RU', label: 'ქართული + Русский' }, { value: 'KA-EN', label: 'ქართული + English' }, { value: 'KA', label: 'ქართული' }];
const TONE = { sent: 'blue', signed: 'ok', cancelled: 'grey' } as const;
const absolute = (p: string) => `${window.location.origin}${p}`;

function CompanySignature() {
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['nda-company-sig'], queryFn: () => http.get<CompanySig>('/ndas/company-signature') });
  const [edit, setEdit] = useState(false);
  const [ink, setInk] = useState(false);
  const pad = useRef<HTMLCanvasElement>(null);
  const save = useMutation({
    mutationFn: () => http.put<CompanySig>('/ndas/company-signature', { signature: signaturePng(pad.current!) }),
    onSuccess: () => { setEdit(false); qc.invalidateQueries({ queryKey: ['nda-company-sig'] }); toast('Подпись компании сохранена'); },
    onError: (e) => toast(errText(e), true),
  });
  const boss = user && ['superadmin', 'superagent'].includes(user.role);
  const d = q.data;
  return (
    <Card label="Один раз" title="Подпись компании (Давид Тибелашвили)">
      {q.isLoading ? <Loading /> : (
        <div className="col gap">
          {d?.signature && !edit && (
            <div className="row row-wrap gap" style={{ alignItems: 'center' }}>
              <img src={d.signature} alt="" style={{ height: 56, background: '#fff', border: '1px solid var(--line, #e3e8f0)', borderRadius: 8, padding: 4 }} />
              <span className="muted" style={{ fontSize: 13 }}>Ставится в каждое новое соглашение · {d.by_name || '—'}, {fmtDate(d.at)}</span>
            </div>
          )}
          {!d?.signature && !edit && <span className="muted">Подписи ещё нет — без неё соглашение не отправить.</span>}
          {edit && <>
            <SignaturePad padRef={pad} onInk={setInk} clearLabel="Стереть" />
            <div className="row gap-sm">
              <Button disabled={!ink} loading={save.isPending} onClick={() => save.mutate()}>Сохранить подпись</Button>
              <Button variant="ghost" onClick={() => setEdit(false)}>Отмена</Button>
            </div>
          </>}
          {!edit && (boss
            ? <div><Button variant="secondary" onClick={() => setEdit(true)}>{d?.signature ? 'Заменить подпись' : 'Расписаться за компанию'}</Button></div>
            : !d?.signature && <span className="faint" style={{ fontSize: 12 }}>Расписаться может только суперадмин.</span>)}
        </div>
      )}
    </Card>
  );
}

function LinkActions({ n }: { n: Nda }) {
  const toast = useToast();
  if (!n.path) return null;
  const url = absolute(n.path);
  const text = `Homes in Georgia: соглашение для подписи — ${n.full_name}`;
  const share = async () => {
    if (navigator.share) { try { await navigator.share({ url, title: text }); } catch { /* closed */ } return; }
    await navigator.clipboard?.writeText(url).then(() => toast('Ссылка скопирована'), () => undefined);
  };
  return (
    <div className="row row-wrap gap-sm">
      <Button size="sm" variant="secondary" onClick={share}><Share2 size={14} />Отправить</Button>
      <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(url).then(() => toast('Ссылка скопирована'), () => undefined)}><Copy size={14} />Копировать</Button>
      <a className="btn btn-sm btn-ghost" href={`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`} target="_blank" rel="noreferrer"><Send size={14} />Telegram</a>
    </div>
  );
}

const ROLES = [{ value: 'recruit', label: 'Рекрут (учебные сделки)' }, { value: 'agent', label: 'Агент' }, { value: 'mentor', label: 'Наставник' }];
const LEVELS = ['25', '50', '70', '90'].map((v) => ({ value: v, label: `Уровень ${v}` }));
const today = () => new Date().toLocaleDateString('sv-SE');  // YYYY-MM-DD

function NewNda({ onMade }: { onMade: (n: Nda) => void }) {
  const toast = useToast();
  const blank = { full_name: '', full_name_ka: '', personal_id: '', ie: '', address: '', phone: '', email: '', telegram: '', iban_gel: '', iban_usd: '' };
  const [f, setF] = useState({ ...blank, role: 'recruit', level: '25', access: today(), lang: 'KA-RU' });
  const m = useMutation({
    mutationFn: () => http.post<Nda>('/ndas', f),
    onSuccess: (n) => { onMade(n); setF({ ...f, ...blank, access: today() }); toast('Соглашение создано — отправьте ссылку агенту'); },
    onError: (e) => toast(errText(e), true),
  });
  const sig = useQuery({ queryKey: ['nda-company-sig'], queryFn: () => http.get<CompanySig>('/ndas/company-signature') });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const role = (e: React.ChangeEvent<HTMLSelectElement>) => setF({ ...f, role: e.target.value, level: e.target.value === 'recruit' ? '25' : f.level === '25' ? '50' : f.level });
  return (
    <Card label="Новому агенту" title={t('Соглашение о подключении к платформе (ред. {ed})', { ed: sig.data?.edition ?? '…' })}>
      <div className="form-grid">
        <Field label="ФИО агента *" hint="Латиницей или кириллицей, как в паспорте"><Input value={f.full_name} onChange={set('full_name')} placeholder="Nino Beridze" /></Field>
        <Field label="ФИО по-грузински" hint="Для грузинского текста; пусто — как выше"><Input value={f.full_name_ka} onChange={set('full_name_ka')} placeholder="ნინო ბერიძე" /></Field>
        <Field label="Личный номер *"><Input value={f.personal_id} onChange={set('personal_id')} /></Field>
        <Field label="Номер ИП (ი/მ)" hint={t('Пусто — агент добавит в профиле, договор обновится')}><Input value={f.ie} onChange={set('ie')} /></Field>
        <Field label="Юридический адрес"><Input value={f.address} onChange={set('address')} /></Field>
        <Field label="Телефон"><Input type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: phoneInput(e) })} /></Field>
        <Field label="Email"><Input type="email" value={f.email} onChange={set('email')} /></Field>
        <Field label="Telegram" hint="@username: подписать сможет только этот аккаунт"><Input value={f.telegram} onChange={set('telegram')} placeholder="@username" /></Field>
        <Field label="Роль"><Select value={f.role} onChange={role} options={ROLES} /></Field>
        <Field label="Уровень" hint="Приложение 1: доля комиссии у агента"><Select value={f.level} onChange={set('level')} options={LEVELS} /></Field>
        <Field label="Доступ с"><Input type="date" value={f.access} onChange={set('access')} /></Field>
        <Field label="IBAN GEL"><Input value={f.iban_gel} onChange={set('iban_gel')} placeholder="GE…" /></Field>
        <Field label="IBAN USD"><Input value={f.iban_usd} onChange={set('iban_usd')} placeholder="GE…" /></Field>
        <Field label="Язык"><Select value={f.lang} onChange={set('lang')} options={LANGS} /></Field>
      </div>
      <div className="mt"><Button disabled={!f.full_name.trim() || !f.personal_id.trim()} loading={m.isPending} onClick={() => m.mutate()}><ShieldCheck size={16} />Создать ссылку</Button></div>
    </Card>
  );
}


// ---------------------------------------------------------------- this NDA's own text (like a client contract's text
// edited in the wizard's preview): an admin changes / adds / removes clauses while it is not signed; the server
// re-renders and re-hashes it, an open signing page then asks the agent to reload. Georgian is the leading text: an
// edit in one language marks the others «не переведено» until they are edited too (or marked translated).
type Ln = 'ka' | 'ru' | 'en';
type Cell = Record<Ln, string>;
interface Block extends Partial<Cell> { k: string; n?: string; only?: string; todo?: Ln[]; head?: Cell[]; rows?: Cell[][]; _id?: number; _ch?: Ln[] }
interface NdaText { blocks: Block[]; edited: boolean; edition: string; lang: Nda['lang']; status: Nda['status'] }
const ALL: Ln[] = ['ka', 'ru', 'en'];
const KIND: Record<string, string> = { p: 'Абзац', h: 'Глава', n: 'Пункт', li: 'Пункт списка', app: 'Приложение', sub: 'Раздел', t: 'Таблица' };
let uid = 0;
/** Not translated: marked earlier, or another language changed in this edit and this one not (yet). */
const missing = (b: Block): Ln[] => { const ch = b._ch || []; return ALL.filter((l) => !ch.includes(l) && (b.todo?.includes(l) || ch.length > 0)); };

function NdaTextEditor({ n, onClose }: { n: Nda; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const langs: Ln[] = n.lang === 'KA' ? ['ka'] : ['ka', n.lang === 'KA-RU' ? 'ru' : 'en'];
  const [blocks, setBlocks] = useState<Block[] | null>(null);
  const [edited, setEdited] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [find, setFind] = useState('');
  const [preview, setPreview] = useState<string | null>(null);
  const q = useQuery({ queryKey: ['nda-text', n.id], queryFn: () => http.get<NdaText>(`/ndas/${n.id}/text`) });
  useEffect(() => {
    if (q.data && !blocks) { setBlocks(q.data.blocks.map((b) => ({ ...b, _id: ++uid }))); setEdited(q.data.edited); }
  }, [q.data, blocks]);
  const payload = () => ({ blocks: blocks!.map(({ _id, _ch, ...b }) => ({ ...b, todo: missing({ ...b, _ch }) })) });
  const todo = (blocks || []).filter((b) => missing(b).some((l) => langs.includes(l)) && (!b.only || b.only.split(' ').includes(n.lang)));
  const done = () => { qc.invalidateQueries({ queryKey: ['ndas'] }); qc.invalidateQueries({ queryKey: ['nda-text', n.id] }); };
  const save = useMutation({
    mutationFn: (reset: boolean) => http.put<Nda>(`/ndas/${n.id}/text`, reset ? { blocks: null } : payload()),
    onSuccess: (_, reset) => { done(); toast(reset ? t('Вернули стандартный текст соглашения') : t('Текст соглашения сохранён: открытая ссылка попросит агента обновить страницу')); onClose(); },
    onError: (e) => toast(errText(e), true),
  });
  const show = useMutation({
    mutationFn: () => http.post<{ html: string }>(`/ndas/${n.id}/text/preview`, payload()),
    onSuccess: (r) => setPreview(r.html),
    onError: (e) => toast(errText(e), true),
  });
  const patch = (id: number, f: (b: Block) => Block) => { setDirty(true); setBlocks((bs) => bs!.map((b) => (b._id === id ? f(b) : b))); };
  const write = (b: Block, l: Ln, v: string) => patch(b._id!, (x) => ({ ...x, [l]: v, _ch: x._ch?.includes(l) ? x._ch : [...(x._ch || []), l] }));
  // «Перевод готов»: the shown languages count as done (a typo fixed in one language needs no new translation)
  const translated = (b: Block) => patch(b._id!, (x) => ({ ...x, todo: (x.todo || []).filter((l) => !langs.includes(l)), _ch: x._ch?.length ? [...new Set([...x._ch, ...langs])] : x._ch }));
  const add = (after: Block) => { setDirty(true); setBlocks((bs) => { const i = bs!.findIndex((b) => b._id === after._id); const nb: Block = { k: after.k === 'h' ? 'n' : after.k === 't' ? 'p' : after.k, n: '', ka: '', ru: '', en: '', todo: [...ALL], _id: ++uid }; return [...bs!.slice(0, i + 1), nb, ...bs!.slice(i + 1)]; }); };
  const remove = (b: Block) => { if (window.confirm(t('Удалить «{n}» из этого соглашения?', { n: b.n || (b.ka || '').slice(0, 40) }))) { setDirty(true); setBlocks((bs) => bs!.filter((x) => x._id !== b._id)); } };
  const submit = () => {
    if (todo.length && !window.confirm(t('Не переведено пунктов: {n} ({list}). Всё равно сохранить?', { n: todo.length, list: todo.slice(0, 6).map((b) => b.n || KIND[b.k]).join(', ') }))) return;
    save.mutate(false);
  };
  const close = () => { if (!dirty || window.confirm(t('Закрыть без сохранения? Правки пропадут.'))) onClose(); };
  const needle = find.trim().toLowerCase();
  const visible = (blocks || []).filter((b) => (!b.only || b.only.split(' ').includes(n.lang))
    && (!needle || [b.n, ...ALL.map((l) => b[l])].some((x) => (x || '').toLowerCase().includes(needle))));
  return (
    <Modal open wide onClose={close} title={t('Текст соглашения № {num} · {name}', { num: n.number, name: n.full_name })}>
      {!blocks ? <Loading /> : (
        <div className="col gap">
          <div className="muted" style={{ fontSize: 13 }}>
            {t('Правки только для этого агента; стандартный текст (ред. {ed}) не меняется. Грузинский текст — главный. Поля в фигурных скобках ({pid}, {name_ka} …) система заполняет сама.', { ed: q.data?.edition ?? '' })}
            {edited && <> · <b>{t('Текст уже изменён')}</b></>}
          </div>
          {todo.length > 0 && <div className="alert alert-warn">{t('Не переведено: {list}', { list: todo.map((b) => b.n || KIND[b.k]).join(', ') })}</div>}
          <Input value={find} onChange={(e) => setFind(e.target.value)} placeholder={t('Найти пункт: номер или слово')} />
          <div className="col gap-sm">
            {visible.map((b) => {
              const miss = missing(b).filter((l) => langs.includes(l));
              return (
                <div key={b._id} className="card col gap-sm" style={{ padding: 10 }}>
                  <div className="row row-between row-wrap gap-sm">
                    <span className="row gap-sm" style={{ alignItems: 'center' }}>
                      <small className="muted">{t(KIND[b.k] || b.k)}</small>
                      {b.k !== 't' && b.k !== 'p' && b.k !== 'sub' && <Input value={b.n || ''} onChange={(e) => patch(b._id!, (x) => ({ ...x, n: e.target.value }))} style={{ width: 80 }} aria-label={t('Номер')} />}
                      {miss.map((l) => <Badge key={l} tone="warn">{l.toUpperCase()}: {t('не переведено')}</Badge>)}
                    </span>
                    <span className="row gap-sm">
                      {miss.length > 0 && <Button size="sm" variant="ghost" onClick={() => translated(b)}>{t('Перевод готов')}</Button>}
                      <Button size="sm" variant="ghost" onClick={() => add(b)} title={t('Добавить пункт после')}><Plus size={14} />{t('Пункт')}</Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(b)} title={t('Удалить')}><Trash2 size={14} /></Button>
                    </span>
                  </div>
                  {b.k === 't' ? <small className="muted">{t('Таблица: {n} строк, здесь не редактируется', { n: b.rows?.length ?? 0 })}</small> : (
                    <div className="form-grid">
                      {langs.map((l) => (
                        <Field key={l} label={l === 'ka' ? t('Грузинский (главный)') : l === 'ru' ? t('Русский') : t('Английский')}>
                          <Textarea rows={Math.min(8, Math.max(2, Math.ceil((b[l] || '').length / 70)))} value={b[l] || ''} lang={l} onChange={(e) => write(b, l, e.target.value)} />
                        </Field>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="row row-wrap gap-sm" style={{ position: 'sticky', bottom: 0, background: 'var(--card, #fff)', padding: '8px 0' }}>
            <Button loading={save.isPending && !save.variables} onClick={submit}><Save size={16} />{t('Сохранить текст')}</Button>
            <Button variant="secondary" loading={show.isPending} onClick={() => show.mutate()}><Eye size={16} />{t('Предпросмотр')}</Button>
            {edited && <Button variant="ghost" loading={save.isPending && !!save.variables} onClick={() => { if (window.confirm(t('Вернуть стандартный текст? Все правки этого соглашения пропадут.'))) save.mutate(true); }}><RotateCcw size={16} />{t('Стандартный текст')}</Button>}
            <Button variant="ghost" onClick={close}>{t('Закрыть')}</Button>
          </div>
        </div>
      )}
      {preview && (
        <Modal open wide onClose={() => setPreview(null)} title={t('Предпросмотр')}>
          <iframe title={t('Предпросмотр')} srcDoc={preview} sandbox="" style={{ width: '100%', height: '75vh', border: 0, background: '#fff' }} />
        </Modal>
      )}
    </Modal>
  );
}

const TABS = [{ value: 'sent', label: 'Ждут подписи' }, { value: 'signed', label: 'Подписаны' }, { value: 'all', label: 'Все' }] as const;

export function NdasPage() {
  const toast = useToast();
  const { user } = useAuth();
  const admin = !!user && ['superadmin', 'admin'].includes(user.role);
  const [editing, setEditing] = useState<Nda | null>(null);
  const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('sent');
  const [made, setMade] = useState<Nda | null>(null);
  const q = useQuery({ queryKey: ['ndas', tab], queryFn: () => http.get<{ items: Nda[]; total: number }>('/ndas', { status: tab, limit: 100 }) });
  const cancel = useMutation({
    mutationFn: (id: number) => http.post<Nda>(`/ndas/${id}/cancel`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ndas'] }); toast('Соглашение отменено, ссылка больше не работает'); },
    onError: (e) => toast(errText(e), true),
  });
  const pdf = async (n: Nda, amended = false) => {
    const url = URL.createObjectURL(await fetchBlob(`/ndas/${n.id}/pdf${amended ? '?amended=true' : ''}`));
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };
  const rows = itemsOf(q.data);
  return (
    <div className="col gap-lg">
      <div><Link to="/admin" className="muted" style={{ fontSize: 13 }}>← Управление · Пользователи</Link></div>
      <PageHead label="Новые агенты" title="Соглашения (NDA)" />
      <CompanySignature />
      <NewNda onMade={(n) => { setMade(n); setTab('sent'); qc.invalidateQueries({ queryKey: ['ndas'] }); }} />
      {made?.path && (
        <Card label="Готово" title={`Ссылка для ${made.full_name}`}>
          <div className="col gap-sm">
            <a href={absolute(made.path)} target="_blank" rel="noreferrer" style={{ wordBreak: 'break-all' }}>{absolute(made.path)}</a>
            <LinkActions n={made} />
            {admin && <div><Button size="sm" variant="ghost" onClick={() => setEditing(made)}><FileText size={14} />{t('Изменить пункты для этого агента')}</Button></div>}
          </div>
        </Card>
      )}
      <Card label="История" title="Все соглашения">
        <Tabs value={tab} onChange={setTab} tabs={TABS.map((t) => ({ ...t }))} />
        {q.isLoading ? <Loading /> : rows.length === 0 ? <Empty text="Пока пусто" icon={<ShieldCheck size={22} />} /> : (
          <div className="col gap-sm mt">
            {rows.map((n) => (
              <div key={n.id} className="card card-pad col gap-sm" style={{ padding: 12 }}>
                <div className="row row-between row-wrap gap-sm">
                  <span className="col" style={{ gap: 2 }}>
                    <b>{n.full_name}</b>
                    <small className="muted">№ {n.number} · {n.role || '—'} · {n.lang}{n.telegram ? ` · @${n.telegram}` : ''} · {n.created_by?.name || '—'}, {fmtDate(n.created_at)}</small>
                    {n.signed_at && <small className="muted">Подписал(а) {fmtDateTime(n.signed_at)}{n.tg_username ? ` · Telegram @${n.tg_username}` : ''}</small>}
                  </span>
                  <Badge tone={TONE[n.status]}>{n.status_label}</Badge>
                </div>
                <div className="row row-wrap gap-sm">
                  {n.status === 'sent' && <LinkActions n={n} />}
                  {n.status === 'sent' && admin && <Button size="sm" variant="ghost" onClick={() => setEditing(n)}><FileText size={14} />{t('Текст')}</Button>}
                  {n.status === 'sent' && <Button size="sm" variant="ghost" loading={cancel.isPending} onClick={() => { if (window.confirm(`Отменить соглашение для ${n.full_name}? Ссылка перестанет работать.`)) cancel.mutate(n.id); }}><XCircle size={14} />Отменить</Button>}
                  {n.has_pdf && <Button size="sm" variant="secondary" onClick={() => pdf(n).catch((e) => toast(errText(e), true))}><Download size={14} />PDF</Button>}
                  {n.details?.ie_amended && <Button size="sm" variant="secondary" title={t('Подписанное соглашение + дополнение: номер ИП {ie} из профиля', { ie: n.details.ie_amended.ie })} onClick={() => pdf(n, true).catch((e) => toast(errText(e), true))}><Download size={14} />{t('PDF + ИП')}</Button>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      {editing && <NdaTextEditor n={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
