import { reportError } from '../lib/clientLog';
// Small fetch client: /api prefix, JWT bearer from localStorage, 401 → login.
export const TOKEN_KEY = 'hig_token';
export const IS_MOCK = import.meta.env.VITE_MOCK === '1';

export class ApiError extends Error {
  status: number;
  code?: string;
  rid?: string;  // X-Request-Id: the server log line of this request (shown in toasts of 5xx errors)
  data?: Record<string, unknown>;  // extra JSON of the error (possible_duplicate: the objects to look at)
  constructor(status: number, message: string, code?: string, rid?: string, data?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.rid = rid;
    this.data = data;
  }
}

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  if (t !== getToken()) dropMedia();  // logout / another user: his media token goes with the session
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable */ }
}

// ---- the media token. <img> / <video> / <a href> can't send the Authorization header, so file URLs carry ?token=. Not
// the session JWT (a copied photo link would open the whole CRM): a short-lived purpose="media" token that the backend
// takes only from the query and only for GET /api/media/… (deps.current_user). Kept with its expiry and renewed ahead of
// it by the API calls themselves: a response waits for it only while there is none (mediaUrl() is synchronous).
const MEDIA_KEY = 'hig_media_token';
const MEDIA_RENEW_MS = 2 * 3600_000;  // of its 8 h
type MediaToken = { token: string; exp: number };  // exp: ms, from the server's expires_in (no clock-skew guess)
let media: MediaToken | null = (() => {
  try { const m = JSON.parse(localStorage.getItem(MEDIA_KEY) || 'null'); return m?.token && m.exp ? m : null; } catch { return null; }
})();
let mediaFetch: Promise<void> | null = null;
function dropMedia() {
  media = null;
  try { localStorage.removeItem(MEDIA_KEY); } catch { /* storage unavailable */ }
}
const mediaLeft = () => (media ? media.exp - Date.now() : 0);
/** Gets / renews the media token (one request at a time); never throws, a failure leaves file URLs without one. */
export function ensureMediaToken(): Promise<void> {
  const session = getToken();
  if (IS_MOCK || !session || mediaLeft() > MEDIA_RENEW_MS) return Promise.resolve();
  mediaFetch ??= fetch('/api/auth/media-token', { headers: { Authorization: `Bearer ${session}` } })
    .then(async (r) => {
      if (!r.ok || getToken() !== session) return;  // a 401 here is the session's: the API call itself handles it
      const d = (await r.json()) as { token: string; expires_in: number };
      media = { token: d.token, exp: Date.now() + d.expires_in * 1000 };
      try { localStorage.setItem(MEDIA_KEY, JSON.stringify(media)); } catch { /* storage unavailable */ }
    })
    .catch(() => undefined)
    .finally(() => { mediaFetch = null; });
  return mediaFetch;
}
function mediaToken(): string {
  if (mediaLeft() <= MEDIA_RENEW_MS) void ensureMediaToken();
  return mediaLeft() > 0 ? media!.token : '';
}

let onUnauthorized: () => void = () => {
  const path = window.location.pathname;
  if (!path.startsWith('/login')) {
    const back = encodeURIComponent(path + window.location.search);
    window.location.href = `/login?next=${back}`;
  }
};
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

/** Telegram Mini App initData, when the page runs inside Telegram. */
export function telegramInitData(): string {
  const w = window as unknown as { Telegram?: { WebApp?: { initData?: string } } };
  return w.Telegram?.WebApp?.initData || '';
}

let reauth: Promise<boolean> | null = null;
/** Inside Telegram an expired token is renewed from initData instead of sending the user to /login. */
function telegramReauth(): Promise<boolean> {
  const initData = telegramInitData();
  if (!initData) return Promise.resolve(false);
  reauth ??= fetch('/api/auth/telegram-webapp', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ init_data: initData }),
  }).then(async (r) => {
    if (!r.ok) return false;
    const d = (await r.json()) as { token?: string; access_token?: string };
    const t = d.access_token ?? d.token;
    if (t) setToken(t);
    return !!t;
  }).catch(() => false).finally(() => { setTimeout(() => { reauth = null; }, 0); });
  return reauth;
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>;

function qs(q?: Query): string {
  if (!q) return '';
  const p = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));  // ?source=ss&source=myhome
    else if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

const ERROR_TEXT: Record<string, string> = {
  already_taken: 'Заявку уже взял другой оператор',
  taken_by_other: 'Объект уже взят другим агентом',
  not_registered: 'Ваш Telegram не зарегистрирован в системе. Обратитесь к администратору',
  invalid_credentials: 'Неверный логин или пароль',
  forbidden: 'Нет доступа к этой странице или действию',
  not_found: 'Не найдено: запись удалена или ссылка устарела',
  submitted: 'Объект уже у оператора: фото и чек-лист теперь меняет только он',
  publish_failed: 'Telegram не принял пост. Проверьте настройки канала и повторите',
  exclusive_conflict: 'Эксклюзив ещё висит на других сайтах. Попросите собственника снять объявление, затем оператор отмечает «Проверено: снято»',
};

let keepaliveNow = false;
/** Requests started synchronously inside fn go out with fetch keepalive: they outlive the page (autosave on pagehide). */
export function withKeepalive<T>(fn: () => T): T {
  keepaliveNow = true;
  try { return fn(); } finally { keepaliveNow = false; }
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query, retried = false): Promise<T> {
  const keepalive = keepaliveNow;  // read before the first await
  const url = path + qs(query);
  if (IS_MOCK) {
    const { mockFetch } = await import('./mock/server');
    try {
      return (await mockFetch(method, url, body)) as T;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onUnauthorized();
      throw e;
    }
  }
  // the data may hold file URLs: without a valid media token it waits for one (fetched alongside), else renewal is in background
  const mediaReady = mediaLeft() <= 0 ? ensureMediaToken() : (void ensureMediaToken(), null);
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`/api${url}`, { method, headers, body: payload, keepalive });
  } catch (e) {
    reportError({ kind: 'network', message: String(e), api_path: `${method} ${path}` });
    throw new ApiError(0, 'Нет связи с сервером. Проверьте интернет и повторите', 'network');
  }
  const rid = res.headers.get('X-Request-Id') || undefined;
  if (res.status === 401 && !path.startsWith('/auth/')) {
    setToken(null);
    if (!retried && (await telegramReauth())) return request<T>(method, path, body, query, true);
    onUnauthorized();
    throw new ApiError(401, 'Требуется вход');
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!res.ok) {
    const d = data as { detail?: unknown; code?: string; message?: string; data?: Record<string, unknown> } | null;
    if (res.status === 401 && path === '/auth/login') throw new ApiError(401, 'Неверный логин или пароль', 'invalid_credentials');
    if (res.status === 401 && path.startsWith('/auth/telegram')) throw new ApiError(401, 'Не удалось войти через Telegram. Попробуйте ещё раз', 'unauthorized');
    if (res.status === 401) throw new ApiError(401, 'Сессия истекла, войдите снова', 'unauthorized');
    let code: string | undefined;
    let msg = `Ошибка ${res.status}`;
    if (d && typeof d === 'object') {
      const det = d.detail as { code?: string; message?: string } | string | undefined;
      if (typeof det === 'string') { msg = det; code = d.code || det; }
      else if (det && typeof det === 'object') { code = det.code; msg = det.message || det.code || msg; }
      else if (d.message) { msg = d.message; code = d.code; }
      if (Array.isArray(d.detail)) msg = 'Проверьте поля формы';
    }
    if (code && ERROR_TEXT[code]) msg = ERROR_TEXT[code];
    if (res.status >= 500) reportError({ kind: 'api', message: msg, api_path: `${method} ${path}`, api_status: res.status, api_rid: rid });
    throw new ApiError(res.status, msg, code, rid, d && typeof d === 'object' ? d.data : undefined);
  }
  if (mediaReady) await mediaReady;
  return data as T;
}

/** A file from an authenticated endpoint (contract PDFs). */
export async function fetchBlob(path: string): Promise<Blob> {
  if (IS_MOCK) {  // a mock route may answer {__html} (e.g. /sign-docs/:id/pdf): opened as a page instead of a PDF
    const { mockFetch } = await import('./mock/server');
    const r = (await mockFetch('GET', path)) as { __html?: string } | null;
    if (r?.__html) return new Blob([r.__html], { type: 'text/html' });
    throw new ApiError(404, 'Файл не найден');
  }
  const token = getToken();
  const res = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, res.status === 404 ? 'Файл не найден' : `Ошибка ${res.status}`);
  return res.blob();
}

export const http = {
  get: <T>(p: string, q?: Query) => request<T>('GET', p, undefined, q),
  post: <T>(p: string, b?: unknown, q?: Query) => request<T>('POST', p, b ?? {}, q),
  patch: <T>(p: string, b?: unknown) => request<T>('PATCH', p, b ?? {}),
  put: <T>(p: string, b?: unknown) => request<T>('PUT', p, b ?? {}),
  del: <T>(p: string) => request<T>('DELETE', p),
};

/** Accept either `{items,total}` or a bare array. */
export function itemsOf<T>(d: { items: T[] } | T[] | undefined | null): T[] {
  if (!d) return [];
  return Array.isArray(d) ? d : d.items || [];
}

/** The ~640px preview for cards, lists and thumbnails (the API serves the original while there is none);
 * mediaUrl() stays for the full-screen lightbox. */
export function thumbUrl(path?: string | null): string {
  const u = mediaUrl(path);
  return /^\/api\/(media|listing-photos)\//.test(u) ? `${u}${u.includes('?') ? '&' : '?'}p=1` : u;
}

/** A file's URL for <img> / <video> / <a>: /api/media/… gets the media token (see above); other /api/ files (listing
 * photos, /public/ PDFs) need no login and get none. */
export function mediaUrl(path?: string | null): string {
  if (!path) return '';
  if (path.startsWith('/api/')) {
    const tk = path.startsWith('/api/media/') && !path.includes('token=') ? mediaToken() : '';
    return tk ? `${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(tk)}` : path;
  }
  if (/^(https?:|data:|blob:|\/)/.test(path)) return path;
  const t = mediaToken();
  return `/api/media/${path}${t ? `?token=${encodeURIComponent(t)}` : ''}`;
}

/** POST a FormData with upload progress (fetch has none): `onProgress` gets 0..1. Errors as ApiError, like request(). */
export function uploadWithProgress<T>(path: string, body: FormData, onProgress: (f: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', `/api${path}`);
    const token = getToken();
    if (token) x.setRequestHeader('Authorization', `Bearer ${token}`);
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    x.onerror = () => reject(new ApiError(0, 'Нет связи с сервером, попробуйте ещё раз'));
    x.onload = () => {
      let d: { detail?: unknown; code?: string } | null = null;
      try { d = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status >= 200 && x.status < 300) { resolve(d as T); return; }
      if (x.status === 401) { onUnauthorized(); reject(new ApiError(401, 'Сессия истекла, войдите снова', 'unauthorized')); return; }
      const msg = typeof d?.detail === 'string' ? d.detail : x.status === 413 ? 'Файл слишком большой' : `Ошибка ${x.status}`;
      reject(new ApiError(x.status, msg, d?.code));
    };
    x.send(body);
  });
}
