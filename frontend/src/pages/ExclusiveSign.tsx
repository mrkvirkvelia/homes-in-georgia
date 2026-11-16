// /sign/<token>: the owner confirms the exclusive cooperation and signs with a finger (no CRM login; ported from
// PlatformDGE/hig-sign). The PDF is built here and attached to the object (backend properties.sign_contract).
import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { http } from '../api/client';
import { errText } from '../components/toast';
import { Checkbox, Button, ErrorBox, Field, Input, Loading, Seg } from '../components/ui';
import { LANG_LABEL, buildExclusivePdf, confirmText, tbilisiNow, type Lang } from '../lib/exclusivePdf';
import { fmtDateTime, phoneInput } from '../lib/format';
import { cadastralError, cadastralInput, cadastralNorm } from '../lib/cadastral';
import { CheckCircle2, ExternalLink, Upload } from 'lucide-react';
import { RegistryApps, day, useSettledId, type RegApp, type RegTexts } from '../components/RegistryApps';
import { SignaturePad } from '../components/SignaturePad';
import { ExtractLink, useExtractLink, type ExtractFields } from '../features/contracts/OwnerLookup';
import { setPageLang } from '../lib/i18n';

// draft: what he already typed / gave on this link (backend properties.save_sign_draft); null once signed
interface Draft { full_name?: string; personal_id?: string; phone?: string; cadastral_code?: string; lang?: string; extract_url?: string;
  extract_name?: string; id_doc_name?: string; registry_app?: RegApp | null }
interface SignView { id: number; address: string; cadastral_code: string; owner_name: string; owner_phone: string; signed_at: string | null; draft?: Draft | null }
type Form = { full_name: string; personal_id: string; phone: string; cadastral_code: string };

// the registry extract: our backend lists NAPR's applications for the code (services/registry.py); the owner taps one,
// NAPR's own page opens with its reCAPTCHA, he downloads the extract (ამონაწერი) himself and uploads it here
const REGISTRY_URL = 'https://naprweb.reestri.gov.ge/_dea/#/search';
const MAX_DOC = 15 * 1024 * 1024;
type Docs = RegTexts & { fromExtract: string; upload: string; extract: string; extractHow: string; openRegistry: string; passport: string; passportHint: string; pick: string; replace: string; tooBig: string };
const DOCS: Record<Lang, Docs> = {
  ka: { fromExtract: 'საკადასტრო კოდი ამონაწერიდან', listTitle: 'თქვენი განცხადებები საჯარო რეესტრში', listHint: 'შეეხეთ ამ ობიექტის ბოლო დასრულებულ განცხადებას: გაიხსნება რეესტრის გვერდი — მონიშნეთ „მე არ ვარ რობოტი“, დააკოპირეთ ამონაწერის ბმული (ჩამოტვირთვის ღილაკი: ხანგრძლივი დაჭერა → „ბმულის კოპირება“) და დაბრუნდით აქ — ამონაწერი თავად ჩაიტვირთება. ან ჩამოტვირთეთ PDF და ატვირთეთ ქვემოთ.', open: 'გახსნა', picked: 'არჩეულია', more: 'მეტის ჩვენება', none: 'ამ პირადი ნომრით განცხადებები ვერ მოიძებნა.', down: 'რეესტრი ახლა არ პასუხობს.', upload: 'ჩამოტვირთული ამონაწერის ატვირთვა', extract: 'საჯარო რეესტრის ამონაწერი (PDF)', extractHow: 'გახსენით რეესტრი, ჩაწერეთ პირადი ნომერი, გახსენით ამ ობიექტის ბოლო განცხადება და ჩამოტვირთეთ ამონაწერი (PDF), შემდეგ ატვირთეთ აქ.', openRegistry: 'რეესტრის გახსნა', passport: 'პასპორტი / პირადობის მოწმობა', passportHint: 'ფოტო ან PDF (JPG, PNG, HEIC, PDF), 15 მბ-მდე. ინახება დახურულად, ხედავს მხოლოდ სააგენტო.', pick: 'ფაილის არჩევა', replace: 'შეცვლა', tooBig: 'ფაილი 15 მბ-ზე დიდია' },
  ru: { fromExtract: 'Кадастровый код из выписки', listTitle: 'Ваши заявки в Публичном реестре', listHint: 'Нажмите на последнюю завершённую заявку по этому объекту: откроется страница реестра — отметьте «Я не робот», скопируйте ссылку на выписку (кнопка скачивания: долгое нажатие → «Скопировать ссылку») и вернитесь сюда — выписка загрузится сама. Или скачайте PDF и загрузите его ниже.', open: 'Открыть', picked: 'Выбрано', more: 'Показать ещё', none: 'По этому личному номеру заявок не найдено.', down: 'Реестр сейчас не отвечает.', upload: 'Загрузите скачанную выписку', extract: 'Выписка из Публичного реестра (PDF)', extractHow: 'Откройте реестр, введите личный номер, откройте последнюю заявку по этому объекту и скачайте выписку (ამონაწერი, PDF), затем загрузите её сюда.', openRegistry: 'Открыть реестр', passport: 'Паспорт / ID-карта', passportHint: 'Фото или PDF (JPG, PNG, HEIC, PDF), до 15 МБ. Хранится закрыто, видит только агентство.', pick: 'Выбрать файл', replace: 'Заменить', tooBig: 'Файл больше 15 МБ' },
  en: { fromExtract: 'Cadastral code from the extract', listTitle: 'Your applications in the Public Registry', listHint: 'Tap the latest completed application for this property: the registry page opens — tick “I’m not a robot”, copy the extract’s link (download button: long press → “Copy link”) and come back — the extract loads by itself. Or download the PDF and upload it below.', open: 'Open', picked: 'Selected', more: 'Show more', none: 'No applications found for this personal ID.', down: 'The registry is not responding right now.', upload: 'Upload the downloaded extract', extract: 'Public Registry extract (PDF)', extractHow: 'Open the registry, enter your personal ID, open the latest application for this property and download the extract (ამონაწერი, PDF), then upload it here.', openRegistry: 'Open the registry', passport: 'Passport / ID card', passportHint: 'Photo or PDF (JPG, PNG, HEIC, PDF), up to 15 MB. Stored privately, only the agency sees it.', pick: 'Choose file', replace: 'Replace', tooBig: 'The file is larger than 15 MB' },
};

function FilePick({ label, hint, accept, file, busy, onFile, t }: { label: string; hint?: React.ReactNode; accept: string; file: string; busy?: boolean; onFile: (f: File) => void; t: Docs }) {
  const ref = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState('');
  return (
    <div className="col gap-sm">
      <span className="label">{label}</span>
      {hint && <span className="faint" style={{ fontSize: 12 }}>{hint}</span>}
      <input ref={ref} type="file" accept={accept} hidden onChange={(e) => {
        const fl = e.target.files?.[0] || null; e.target.value = '';
        if (fl && fl.size > MAX_DOC) setErr(t.tooBig); else if (fl) { setErr(''); onFile(fl); }
      }} />
      <div className="row row-wrap gap-sm">
        <Button variant={file ? 'secondary' : 'primary'} loading={busy} onClick={() => ref.current?.click()}><Upload size={16} />{file ? t.replace : t.pick}</Button>
        {file && <span className="row gap-sm" style={{ minWidth: 0, overflowWrap: 'anywhere' }}><CheckCircle2 size={16} color="var(--ok, #1a7f4b)" />{file}</span>}
      </div>
      {err && <span style={{ color: 'var(--accent)', fontSize: 12 }}>{err}</span>}
    </div>
  );
}

type UiT = { name: string; pid: string; phone: string; cad: string; cadBad: string; sign: string; clear: string; agree: string; send: string; done: string; saved: string; extractSaved: string; or: string };
const UI: Record<Lang, UiT> = {
  ru: { saved: 'Сохранено как черновик — можно закрыть страницу и вернуться по этой же ссылке', extractSaved: 'Выписка сохранена', or: 'Или загрузите скачанный PDF', name: 'ФИО', pid: 'Личный номер', phone: 'Телефон', cad: 'Кадастровый код', cadBad: 'Проверьте код: цифры через точку, например 01.14.12.003.045', sign: 'Подпишите пальцем', clear: 'Стереть', agree: 'С условиями согласен(на)', send: 'Подписать', done: 'Договор подписан. Спасибо!' },
  ka: { saved: 'შენახულია მონახაზად — შეგიძლიათ დახუროთ გვერდი და დაბრუნდეთ იმავე ბმულით', extractSaved: 'ამონაწერი შენახულია', or: 'ან ატვირთეთ ჩამოტვირთული PDF', name: 'სახელი და გვარი', pid: 'პირადი ნომერი', phone: 'ტელეფონი', cad: 'საკადასტრო კოდი', cadBad: 'შეამოწმეთ კოდი: ციფრები წერტილით, მაგ. 01.14.12.003.045', sign: 'მოაწერეთ ხელი თითით', clear: 'წაშლა', agree: 'ვეთანხმები ზემოთ აღნიშნულ პირობებს', send: 'ხელმოწერა', done: 'ხელშეკრულება ხელმოწერილია. გმადლობთ!' },
  en: { saved: 'Saved as a draft — you can close the page and come back by the same link', extractSaved: 'Extract saved', or: 'Or upload the downloaded PDF', name: 'Full name', pid: 'Personal ID number', phone: 'Phone', cad: 'Cadastral code', cadBad: 'Check the code: digits separated by dots, e.g. 01.14.12.003.045', sign: 'Sign with your finger', clear: 'Clear', agree: 'I agree to the above terms', send: 'Sign', done: 'Signed. Thank you!' },
};

export function ExclusiveSignPage() {
  const { token = '' } = useParams();
  const base = `/public/exclusive/${token}`;
  const q = useQuery({ queryKey: ['exclusive-sign', token], queryFn: () => http.get<SignView>(base), retry: false, refetchOnWindowFocus: false });
  const [lang, setLang] = useState<Lang>('ka');
  setPageLang(lang);  // the extract link / registry list below speak the page's language
  const [f, setF] = useState<Form>({ full_name: '', personal_id: '', phone: '', cadastral_code: '' });
  const [ink, setInk] = useState(false);
  const [agree, setAgree] = useState(false);
  // the files are kept on the server the moment he gives them (the draft): only their names live here
  const [idDoc, setIdDoc] = useState('');
  const [extract, setExtract] = useState('');
  const [busy, setBusy] = useState<'' | 'id' | 'extract'>('');
  const [fileErr, setFileErr] = useState('');
  const [app, setApp] = useState<RegApp | null>(null);
  const [fromExtract, setFromExtract] = useState<string | null | undefined>(undefined);  // undefined: not read yet
  const [ready0, setReady0] = useState(false);  // the draft is applied: from here on every change autosaves
  const [savedAt, setSavedAt] = useState(false);
  const lookup = useSettledId(f.personal_id);
  const pad = useRef<HTMLCanvasElement>(null);
  const chain = useRef<Promise<unknown>>(Promise.resolve());  // draft saves and uploads one after another
  const queue = <T,>(fn: () => Promise<T>): Promise<T> => { const r = chain.current.then(fn); chain.current = r.catch(() => undefined); return r; };
  useEffect(() => {
    const v = q.data;
    if (!v || ready0) return;
    const d = v.draft || {};
    setF({ full_name: d.full_name || v.owner_name, personal_id: d.personal_id || '', phone: d.phone || v.owner_phone, cadastral_code: d.cadastral_code || v.cadastral_code });
    if (d.lang === 'ru' || d.lang === 'ka' || d.lang === 'en') setLang(d.lang);
    if (d.registry_app?.app_id) setApp(d.registry_app);
    setExtract(d.extract_name || ''); setIdDoc(d.id_doc_name || '');
    if (d.extract_url) link.setUrl(d.extract_url);
    if (d.extract_name && d.cadastral_code) setFromExtract(d.cadastral_code);
    setReady0(true);
  }, [q.data, ready0]);
  // autosave (700 ms after the last keystroke; at once when he leaves the tab for the registry or closes it)
  const pending = useRef<Record<string, unknown> | null>(null);
  const flush = useCallback(() => {
    const body = pending.current;
    if (!body) return;
    pending.current = null;
    void queue(() => http.put(`${base}/draft`, body)).then(() => setSavedAt(true), () => undefined);
  }, [base]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!ready0 || q.data?.signed_at) return;
    pending.current = { ...f, lang, registry_app: app };
    const h = setTimeout(flush, 700);
    return () => clearTimeout(h);
  }, [f, lang, app, ready0]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const out = () => { if (document.visibilityState === 'hidden') flush(); };
    document.addEventListener('visibilitychange', out);
    window.addEventListener('pagehide', flush);
    return () => { document.removeEventListener('visibilitychange', out); window.removeEventListener('pagehide', flush); };
  }, [flush]);
  const t = UI[lang], td = DOCS[lang];
  // the extract by its link, as in the contract wizard: the server downloads it, keeps it with the draft, the code
  // always and the empty name / ID fill in
  const fNow = useRef(f);
  fNow.current = f;
  const onFields = (x: ExtractFields) => {
    const cur = fNow.current, n = { ...cur }, names: string[] = [];
    if (x.cadastral_code) { n.cadastral_code = x.cadastral_code; names.push(t.cad); }
    if (x.owner_full_name && !cur.full_name.trim()) { n.full_name = x.owner_full_name; names.push(t.name); }
    if (x.owner_personal_number && !cur.personal_id.trim()) { n.personal_id = x.owner_personal_number; names.push(t.pid); }
    setF(n);
    if (x.cadastral_code) setFromExtract(x.cadastral_code);
    return names;
  };
  const link = useExtractLink(q.data?.draft?.extract_url, onFields, () => setExtract('extract.pdf'), `${base}/extract-from-url`, t.extractSaved);
  const goLink = (u: string) => queue(() => link.go(u));
  // or the downloaded PDF: the code is read from it (backend registry.extract_code), he doesn't type it
  const pickExtract = (fl: File) => {
    setFromExtract(undefined); setBusy('extract'); setFileErr('');
    const fd = new FormData(); fd.append('file', fl);
    queue(() => http.post<{ cadastral_code: string | null; name: string }>(`${base}/extract-code`, fd)).then((r) => {
      setExtract(r.name || fl.name); setFromExtract(r.cadastral_code);
      if (r.cadastral_code) setF((x) => ({ ...x, cadastral_code: r.cadastral_code! }));
    }, (e) => { setFromExtract(null); setFileErr(errText(e)); }).finally(() => setBusy(''));
  };
  const pickId = (fl: File) => {
    setBusy('id'); setFileErr('');
    const fd = new FormData(); fd.append('file', fl);
    queue(() => http.post<Draft>(`${base}/id-doc`, fd)).then((r) => setIdDoc(r.id_doc_name || fl.name), (e) => setFileErr(errText(e))).finally(() => setBusy(''));
  };
  const sign = useMutation({
    mutationFn: async () => {
      const v = q.data!;
      flush();
      await chain.current;  // the last draft save / upload lands first: the files are taken from the draft
      const pdf = await buildExclusivePdf(v.id, { ...f, address: v.address, date: tbilisiNow() }, pad.current!, navigator.userAgent,
        [['პასპორტი / Паспорт (ID)', `загружен: ${idDoc}`], ['ამონაწერი / Выписка из реестра', `загружена: ${extract}`],
          ...(app ? [['განცხადება / Заявка NAPR', `№${app.reg_number} · ${day(app.date)}`] as [string, string]] : [])]);
      const fd = new FormData();
      Object.entries(f).forEach(([k, val]) => fd.append(k, val.trim()));
      fd.append('consent', 'true');
      fd.append('file', new Blob([pdf], { type: 'application/pdf' }), `exclusive-${v.id}.pdf`);
      if (app) fd.append('registry_app', JSON.stringify(app));
      return http.post<SignView>(base, fd);
    },
    onSuccess: () => q.refetch(),
  });

  const wrap = (body: React.ReactNode) => <div style={{ maxWidth: 640, margin: '0 auto', padding: '24px 16px' }}><div className="card card-pad col gap-lg">{body}</div></div>;
  if (q.isLoading) return wrap(<Loading />);
  if (q.error || !q.data) return wrap(<ErrorBox error={q.error} />);
  if (q.data.signed_at) return wrap(<div className="alert alert-ok">{t.done} · {fmtDateTime(q.data.signed_at)}</div>);
  const [title, lines] = confirmText(lang, { ...f, address: q.data.address, date: tbilisiNow().split(',')[0] });
  const cadBad = !!cadastralError(f.cadastral_code, q.data?.cadastral_code);
  const ready = f.full_name.trim() && f.personal_id.trim() && f.phone.trim() && ink && agree && !cadBad && idDoc && extract && !busy;
  return wrap(<>
    <div className="row row-between row-wrap gap-sm">
      <b style={{ color: '#1D3560' }}>Homes in Georgia · Rent in Tbilisi</b>
      <Seg value={lang} onChange={setLang} options={(Object.keys(LANG_LABEL) as Lang[]).map((l) => ({ value: l, label: LANG_LABEL[l] }))} />
    </div>
    <div className="form-grid">
      <Field label={t.name}><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
      <Field label={t.pid}><Input inputMode="numeric" value={f.personal_id} onChange={(e) => setF({ ...f, personal_id: e.target.value })} /></Field>
      <Field label={t.phone}><Input type="tel" inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: phoneInput(e) })} /></Field>
    </div>
    <ExtractLink x={{ ...link, go: goLink }} />
    <RegistryApps base={`${base}/registry`} personalId={lookup} picked={app} onPick={setApp} t={td}
      onCode={(code) => { setF((x) => ({ ...x, cadastral_code: code })); setFromExtract(code); }} onLink={goLink} />
    <div className="col gap-sm">
      <FilePick label={extract ? td.extract : t.or} accept="application/pdf,.pdf" file={extract} busy={busy === 'extract'} onFile={pickExtract} t={td} hint={app || extract ? undefined : <>
        {td.extractHow}
        <span className="row row-wrap gap-sm" style={{ marginTop: 8 }}>
          <a className="btn btn-secondary btn-sm" href={REGISTRY_URL} target="_blank" rel="noreferrer"><ExternalLink size={14} />{td.openRegistry}</a>
        </span>
      </>} />
      {extract && fromExtract && <div className="alert alert-ok">{td.fromExtract}: <b>{fromExtract}</b></div>}
      {extract && fromExtract === null && !q.data.cadastral_code && <div className="form-grid"><Field label={t.cad} hint={cadBad ? <span style={{ color: 'var(--accent)' }}>{t.cadBad}</span> : undefined}><Input value={f.cadastral_code} placeholder="01.14.12.003.045" onChange={(e) => setF({ ...f, cadastral_code: cadastralInput(e) })} onBlur={() => { if (!cadBad && f.cadastral_code !== q.data?.cadastral_code) setF({ ...f, cadastral_code: cadastralNorm(f.cadastral_code) }); }} /></Field></div>}
    </div>
    <FilePick label={td.passport} hint={td.passportHint} accept="image/jpeg,image/png,image/heic,image/heif,.heic,.heif,application/pdf,.pdf" file={idDoc} busy={busy === 'id'} onFile={pickId} t={td} />
    {fileErr && <div className="alert alert-warn">{fileErr}</div>}
    <div className="col gap-sm">
      <h2 style={{ fontSize: 18 }}>{title}</h2>
      {lines.map((s, i) => <div key={i} style={s.startsWith('• ') ? { paddingLeft: 16 } : undefined}>{s}</div>)}
    </div>
    <div className="col gap-sm"><span className="label">{t.sign}</span><SignaturePad padRef={pad} onInk={setInk} clearLabel={t.clear} /></div>
    <Checkbox checked={agree} onChange={setAgree}>{t.agree}</Checkbox>
    {sign.error && <div className="alert alert-warn">{errText(sign.error)}</div>}
    {savedAt && <span className="faint" style={{ fontSize: 12 }}><CheckCircle2 size={12} style={{ verticalAlign: -1 }} /> {t.saved}</span>}
    <Button size="lg" variant="ok" disabled={!ready} loading={sign.isPending} onClick={() => sign.mutate()}>{t.send}</Button>
  </>);
}
