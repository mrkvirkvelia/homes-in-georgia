// /nda/<token>: a new agent signs his NDA (backend services/nda.py, docs/NDA.md) — no CRM login, the link is the access.
// 1) read the agreement; 2) confirm yourself with Telegram (Telegram Login: the app asks to confirm; the server checks
// it, and only the NDA's @username passes); 3) sign with a finger + consent. The signed PDF comes by Telegram and here.
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Download, ShieldCheck } from 'lucide-react';
import { http } from '../api/client';
import { api } from '../api';
import { errText } from '../components/toast';
import { Checkbox, Button, ErrorBox, Field, Input, Loading, Seg } from '../components/ui';
import { SignaturePad, signaturePng } from '../components/SignaturePad';
import { ContractFrame } from '../components/ContractFrame';
import { fmtDateTime } from '../lib/format';

interface NdaView {
  lang: 'KA' | 'KA-RU' | 'KA-EN'; status: 'sent' | 'signed'; full_name: string; personal_id: string; phone: string | null;
  telegram: string | null; role: string | null; doc_sha256: string; confirmed: boolean; tg_username: string | null;
  tg_name: string | null; signed_at: string | null; has_pdf: boolean; test_mode: boolean; html: string | null;
  details: { iban_gel: string; iban_usd: string; ie: string };
}
type L = 'ka' | 'ru' | 'en';
const KEYS = ['iban_gel', 'iban_usd', 'ie'] as const;
const norm = (x: string) => x.replace(/[\s-]/g, '').toUpperCase();
const IBAN_RE = /^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/;  // backend services/nda.IBAN_RE
const IE_RE = /^(\d{9}|\d{11})$/;
const LABEL: Record<L, string> = { ka: 'ქართული', ru: 'Русский', en: 'English' };
const UI: Record<L, Record<string, string>> = {
  ka: { title: 'შეთანხმება პლატფორმასთან მიერთების შესახებ', read: 'გთხოვთ, ყურადღებით წაიკითხოთ შეთანხმება', toSign: 'ხელმოწერაზე გადასვლა ↓',
    step0: '1. თქვენი რეკვიზიტები', iban: 'მიუთითეთ მინიმუმ ერთი ანგარიში — მასზე მიიღებთ ანაზღაურებას.', ie: 'ი/მ ნომერი (არასავალდებულო)', ieHint: 'შეგიძლიათ მოგვიანებით დაამატოთ პროფილში', saveD: 'შენახვა შეთანხმებაში', savedD: 'შენახულია — შეთანხმების ტექსტი განახლდა', needIban: 'მიუთითეთ IBAN (ნაბიჯი 1)', saveFirst: 'შეასწორეთ რეკვიზიტები (ნაბიჯი 1)', saving: 'ვინახავთ…', badIban: 'IBAN: GE + 20 სიმბოლო, მაგ. GE29TB0000000000000000', badIe: '9 ან 11 ციფრი', needTg: 'დაადასტურეთ Telegram-ით (ნაბიჯი 2)',
    step1: '2. დაადასტურეთ თქვენი ვინაობა Telegram-ით', tgBtn: 'Telegram Login', tgBot: 'დადასტურება Telegram-ბოტში', tgBotHint: 'გაიხსნება ბოტი — დააჭირეთ „Start“ და დაბრუნდით აქ.', tgHint: 'Telegram გთხოვთ დადასტურებას აპლიკაციაში.',
    tgOnly: 'მხოლოდ ანგარიში', tgOk: 'დადასტურებულია', step2: '3. მოაწერეთ ხელი თითით', clear: 'წაშლა',
    agree: 'წავიკითხე შეთანხმება და ვეთანხმები მის პირობებს', send: 'ხელმოწერა', done: 'შეთანხმება ხელმოწერილია. გმადლობთ!',
    pdf: 'PDF-ის ჩამოტვირთვა', pdfWait: 'PDF მზადდება, განაახლეთ გვერდი ერთ წუთში.', sent: 'ხელმოწერილი PDF გამოგეგზავნათ Telegram-ში.',
    you: 'მონაწილე', test: 'დადასტურება (სატესტო რეჟიმი)', noTg: 'Telegram-ის ჩატვირთვა ვერ მოხერხდა. განაახლეთ გვერდი.' },
  ru: { title: 'Соглашение о подключении к платформе', read: 'Пожалуйста, внимательно прочитайте соглашение', toSign: 'К подписи ↓',
    step0: '1. Ваши реквизиты', iban: 'Укажите хотя бы один счёт — на него будут приходить выплаты.', ie: 'Номер ИП (ი/მ), необязательно', ieHint: 'Можно добавить позже в профиле', saveD: 'Внести в соглашение', savedD: 'Сохранено — текст соглашения обновлён', needIban: 'Укажите IBAN (шаг 1)', saveFirst: 'Исправьте реквизиты (шаг 1)', saving: 'Сохраняем…', badIban: 'IBAN: GE + 20 символов, например GE29TB0000000000000000', badIe: '9 или 11 цифр', needTg: 'Подтвердите себя через Telegram (шаг 2)',
    step1: '2. Подтвердите себя через Telegram', tgBtn: 'Telegram Login', tgBot: 'Подтвердить в Telegram-боте', tgBotHint: 'Откроется бот — нажмите «Start» и вернитесь сюда.', tgHint: 'Telegram попросит подтвердить вход в приложении.',
    tgOnly: 'Только аккаунт', tgOk: 'Подтверждено', step2: '3. Распишитесь пальцем', clear: 'Стереть',
    agree: 'Я прочитал(а) соглашение и согласен(на) с его условиями', send: 'Подписать', done: 'Соглашение подписано. Спасибо!',
    pdf: 'Скачать PDF', pdfWait: 'PDF готовится, обновите страницу через минуту.', sent: 'Подписанный PDF отправлен вам в Telegram.',
    you: 'Участник', test: 'Подтвердить (тестовый режим)', noTg: 'Не удалось загрузить Telegram. Обновите страницу.' },
  en: { title: 'Platform Agreement', read: 'Please read the agreement carefully', toSign: 'Go to signing ↓',
    step0: '1. Your details', iban: 'Enter at least one account — your payouts go there.', ie: 'IE number (ი/მ), optional', ieHint: 'You can add it later in your profile', saveD: 'Put into the agreement', savedD: 'Saved — the agreement text is updated', needIban: 'Enter an IBAN (step 1)', saveFirst: 'Fix the details (step 1)', saving: 'Saving…', badIban: 'IBAN: GE + 20 characters, e.g. GE29TB0000000000000000', badIe: '9 or 11 digits', needTg: 'Confirm yourself with Telegram (step 2)',
    step1: '2. Confirm yourself with Telegram', tgBtn: 'Telegram Login', tgBot: 'Confirm in the Telegram bot', tgBotHint: 'The bot opens — press «Start» and come back here.', tgHint: 'Telegram will ask you to confirm in the app.',
    tgOnly: 'Only the account', tgOk: 'Confirmed', step2: '3. Sign with your finger', clear: 'Clear',
    agree: 'I have read the agreement and agree to its terms', send: 'Sign', done: 'Agreement signed. Thank you!',
    pdf: 'Download PDF', pdfWait: 'The PDF is being prepared, refresh in a minute.', sent: 'The signed PDF was sent to you in Telegram.',
    you: 'Participant', test: 'Confirm (test mode)', noTg: 'Could not load Telegram. Refresh the page.' },
};

type TgUser = Record<string, string | number>;
type TgLogin = { auth: (o: { bot_id: string; request_access?: string }, cb: (u: TgUser | false) => void) => void };
function loadTelegram(): Promise<TgLogin> {
  const w = window as unknown as { Telegram?: { Login?: TgLogin } };
  if (w.Telegram?.Login) return Promise.resolve(w.Telegram.Login);
  return new Promise((ok, fail) => {
    const s = document.createElement('script');
    s.src = 'https://telegram.org/js/telegram-widget.js?22';
    s.async = true;
    s.onload = () => (w.Telegram?.Login ? ok(w.Telegram.Login) : fail(new Error('no Telegram')));
    s.onerror = () => fail(new Error('no Telegram'));
    document.head.appendChild(s);
  });
}

export function NdaSignPage() {
  const { token = '' } = useParams();
  // until Telegram is confirmed (in the bot, another app) the page checks every few seconds and when it's back in front
  const q = useQuery({ queryKey: ['nda', token], queryFn: () => http.get<NdaView>(`/public/nda/${token}`), retry: false,
    refetchOnWindowFocus: (qq) => !(qq.state.data as NdaView | undefined)?.confirmed,
    refetchInterval: (qq) => { const d = qq.state.data as NdaView | undefined; return d && d.status === 'sent' && !d.confirmed ? 3000 : false; } });
  useEffect(() => { loadTelegram().catch(() => undefined); }, []);  // preloaded: the widget's popup opens right from the tap
  const cfg = useQuery({ queryKey: ['app-config'], queryFn: api.config, staleTime: Infinity, retry: false });
  const [lang, setLang] = useState<L | null>(null);
  const [ink, setInk] = useState(false);
  const [agree, setAgree] = useState(false);
  const [err, setErr] = useState('');
  const pad = useRef<HTMLCanvasElement>(null);
  const qc = useQueryClient();
  const v = q.data;
  const [d, setD] = useState({ iban_gel: '', iban_usd: '', ie: '' });
  const [savedOk, setSavedOk] = useState(false);
  useEffect(() => { if (v?.details) setD(v.details); }, [v?.details?.iban_gel, v?.details?.iban_usd, v?.details?.ie]);  // eslint-disable-line react-hooks/exhaustive-deps
  const details = useMutation({
    mutationFn: () => http.post<NdaView>(`/public/nda/${token}/details`, d),
    onSuccess: (r) => { setErr(''); setSavedOk(true); qc.setQueryData(['nda', token], r); },
    onError: (e) => setErr(errText(e)),
  });
  // autosave (Stanislav 11-16): a second after the last keystroke, when every filled field is valid and an IBAN is given
  const bad = { iban_gel: !!norm(d.iban_gel) && !IBAN_RE.test(norm(d.iban_gel)), iban_usd: !!norm(d.iban_usd) && !IBAN_RE.test(norm(d.iban_usd)),
    ie: !!norm(d.ie) && !IE_RE.test(norm(d.ie)) };
  const dirty = !!v && KEYS.some((k) => norm(d[k]) !== norm(v.details?.[k] || ''));
  const valid = !bad.iban_gel && !bad.iban_usd && !bad.ie && !!(norm(d.iban_gel) || norm(d.iban_usd));
  useEffect(() => {
    if (!v || v.status !== 'sent' || !dirty || !valid || details.isPending) return;
    const id = setTimeout(() => details.mutate(), 1000);
    return () => clearTimeout(id);
  }, [d.iban_gel, d.iban_usd, d.ie, dirty, valid, details.isPending]);  // eslint-disable-line react-hooks/exhaustive-deps
  const l: L = lang || (v?.lang === 'KA-EN' ? 'en' : v?.lang === 'KA-RU' ? 'ru' : 'ka');
  const t = UI[l];

  const confirm = useMutation({
    mutationFn: (body: object) => http.post<NdaView>(`/public/nda/${token}/telegram`, body),
    onSuccess: () => { setErr(''); q.refetch(); },
    onError: (e) => setErr(errText(e)),
  });
  const telegram = () => {
    const botId = String(cfg.data?.bot_id || '');
    if (!botId) { setErr(t.noTg); return; }
    loadTelegram().then((tg) => tg.auth({ bot_id: botId, request_access: 'write' }, (u) => { if (u) confirm.mutate(u); }),
      () => setErr(t.noTg));
  };
  const sign = useMutation({
    mutationFn: () => http.post<NdaView>(`/public/nda/${token}`, { signature: signaturePng(pad.current!), consent: true, doc_sha256: v!.doc_sha256 }),
    onSuccess: () => { setErr(''); q.refetch(); },
    onError: (e) => setErr(errText(e)),
  });

  const wrap = (body: React.ReactNode) => <div style={{ maxWidth: 860, margin: '0 auto', padding: '24px 16px' }}><div className="card card-pad col gap-lg">{body}</div></div>;
  if (q.isLoading) return wrap(<Loading />);
  if (q.error || !v) return wrap(<ErrorBox error={q.error} />);
  const hasIban = !!(v.details?.iban_gel || v.details?.iban_usd);
  const ready = v.confirmed && hasIban && !dirty;
  const langs: L[] = v.lang === 'KA' ? ['ka', 'ru', 'en'] : v.lang === 'KA-RU' ? ['ka', 'ru'] : ['ka', 'en'];
  const head = (
    <>
      <div className="row row-between row-wrap gap-sm">
        <b style={{ color: '#1D3560' }}>Homes in Georgia · Rent in Tbilisi</b>
        <Seg value={l} onChange={setLang} options={langs.map((x) => ({ value: x, label: LABEL[x] }))} />
      </div>
      <h2 style={{ fontSize: 20 }}><ShieldCheck size={20} style={{ verticalAlign: -3, marginRight: 6 }} />{t.title}</h2>
      <div className="muted">{t.you}: <b>{v.full_name}</b>{v.telegram ? ` · @${v.telegram}` : ''}</div>
    </>
  );
  if (v.status === 'signed') {
    return wrap(<>
      {head}
      <div className="alert alert-ok"><CheckCircle2 size={16} style={{ verticalAlign: -3 }} /> {t.done} · {fmtDateTime(v.signed_at)}</div>
      {v.has_pdf
        ? <><a className="btn btn-ok btn-lg" href={`/api/public/nda/${token}/pdf?download=1`}><Download size={18} />{t.pdf}</a><span className="muted" style={{ fontSize: 13 }}>{t.sent}</span></>
        : <span className="muted">{t.pdfWait}</span>}
    </>);
  }
  return wrap(<>
    {head}
    <div className="col gap-sm">
      <div className="row row-between row-wrap gap-sm">
        <span className="label">{t.read}</span>
        <Button size="sm" variant="secondary" onClick={() => document.getElementById('nda-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{t.toSign}</Button>
      </div>
      {v.html && <ContractFrame html={v.html} col={l === 'ka' ? 1 : 2} />}
    </div>
    <div className="col gap-sm" id="nda-form">
      <span className="label">{t.step0}</span>
      <span className="muted" style={{ fontSize: 13 }}>{t.iban}</span>
      <div className="form-grid">
        <Field label="IBAN GEL" hint={bad.iban_gel && <span className="text-red">{t.badIban}</span>}><Input value={d.iban_gel} onChange={(e) => { setSavedOk(false); setD({ ...d, iban_gel: e.target.value }); }} placeholder="GE00TB0000000000000000" autoComplete="off" /></Field>
        <Field label="IBAN USD" hint={bad.iban_usd && <span className="text-red">{t.badIban}</span>}><Input value={d.iban_usd} onChange={(e) => { setSavedOk(false); setD({ ...d, iban_usd: e.target.value }); }} placeholder="GE00TB0000000000000000" autoComplete="off" /></Field>
        <Field label={t.ie} hint={bad.ie ? <span className="text-red">{t.badIe}</span> : t.ieHint}><Input inputMode="numeric" value={d.ie} onChange={(e) => { setSavedOk(false); setD({ ...d, ie: e.target.value }); }} /></Field>
      </div>
      {dirty && valid
        ? <span className="muted" style={{ fontSize: 13 }}>{t.saving}</span>
        : !dirty && hasIban && savedOk && <div className="alert alert-ok"><CheckCircle2 size={16} style={{ verticalAlign: -3 }} /> {t.savedD}</div>}
    </div>
    <div className="col gap-sm">
      <span className="label">{t.step1}</span>
      {v.confirmed
        ? <div className="alert alert-ok"><CheckCircle2 size={16} style={{ verticalAlign: -3 }} /> {t.tgOk}: {v.tg_username ? `@${v.tg_username}` : v.tg_name}</div>
        : <>
            <span className="muted" style={{ fontSize: 13 }}>{cfg.data?.bot_username ? t.tgBotHint : t.tgHint}{v.telegram ? ` ${t.tgOnly} @${v.telegram}.` : ''}</span>
            <div className="row row-wrap gap-sm">
              {cfg.data?.bot_username && <a className="btn" href={`https://t.me/${cfg.data.bot_username}?start=nda_${token}`} target="_blank" rel="noreferrer">{t.tgBot}</a>}
              <Button variant={cfg.data?.bot_username ? 'secondary' : undefined} loading={confirm.isPending} onClick={telegram}>{t.tgBtn}</Button>
              {v.test_mode && <Button variant="ghost" loading={confirm.isPending} onClick={() => confirm.mutate({ test: true })}>{t.test}</Button>}
            </div>
          </>}
    </div>
    <div className="col gap-sm">
      <span className="label">{t.step2}</span>
      <SignaturePad padRef={pad} onInk={setInk} clearLabel={t.clear} />
      <Checkbox checked={agree} onChange={setAgree}>{t.agree}</Checkbox>
    </div>
    {!ready && <div className="alert alert-warn">{[!hasIban || dirty ? (dirty && valid ? t.saving : !valid && (bad.iban_gel || bad.iban_usd || bad.ie) ? t.saveFirst : t.needIban) : '', !v.confirmed ? t.needTg : ''].filter(Boolean).join(' · ')}</div>}
    {err && <div className="alert alert-warn">{err}</div>}
    <Button size="lg" variant="ok" disabled={!(ready && ink && agree)} loading={sign.isPending} onClick={() => sign.mutate()}>{t.send}</Button>
  </>);
}
