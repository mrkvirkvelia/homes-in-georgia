// Frontend errors → POST /api/client-log → one line in the server log (docs/DEPLOY.md «Логи»). No UI of its own.
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { getToken, IS_MOCK } from '../api/client';

export const APP_VERSION: string = import.meta.env.VITE_APP_VERSION || 'dev';

interface Report {
  kind: string; message: string; stack?: string; component?: string;
  api_path?: string; api_status?: number; api_rid?: string;
}

// The public pages carry their access token in the path (/sign|esign|nda|invite/<token>), and so do their API calls
// (/api/public/esign/<token>/pdf …): masked before sending; query and hash dropped (Telegram init data, tokens).
const SECRET_PATH = /^((?:[A-Z]+ )?(?:\/api)?\/(?:public\/(?:esign|nda|contracts|exclusive|ics|daily-rent\/ical)|auth\/invite|invite|sign|esign|nda)\/)[^/]+/;
export function safePath(p: string): string {
  return p.split(/[?#]/)[0].replace(SECRET_PATH, '$1***');
}

let sent = 0;
const recent = new Map<string, number>();

export function reportError(r: Report) {
  if (IS_MOCK || sent >= 30) return;  // a broken page in a loop must not flood the log
  const key = `${r.kind}|${r.message}|${r.api_path ?? ''}`;
  const now = Date.now();
  if ((recent.get(key) ?? 0) > now - 10_000) return;
  recent.set(key, now);
  sent += 1;
  const token = getToken();
  try {
    void fetch('/api/client-log', {
      method: 'POST', keepalive: true,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({
        ...r, stack: r.stack?.slice(0, 4000), api_path: r.api_path && safePath(r.api_path),
        url: window.location.origin + safePath(window.location.pathname), version: APP_VERSION,
      }),
    }).catch(() => undefined);
  } catch { /* never throw from the reporter */ }
}

function errParts(e: unknown): { message: string; stack?: string } {
  if (e instanceof Error) return { message: `${e.name}: ${e.message}`, stack: e.stack };
  return { message: typeof e === 'string' ? e : JSON.stringify(e) ?? String(e) };
}

export function installErrorHandlers() {
  window.addEventListener('error', (ev) => {
    if (!ev.error && !ev.message) return;  // a failed <img>/<script> load: not ours to report
    reportError({ kind: 'onerror', ...errParts(ev.error ?? ev.message) });
  });
  window.addEventListener('unhandledrejection', (ev) => {
    reportError({ kind: 'unhandledrejection', ...errParts(ev.reason) });
  });
}

/** Instead of a white screen: a friendly message + reload; the error itself goes to the server log. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(e: unknown, info: ErrorInfo) {
    reportError({ kind: 'react', ...errParts(e), component: info.componentStack?.slice(0, 2000) ?? undefined });
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, textAlign: 'center' }}>
        <div>
          <h2 style={{ marginBottom: 8 }}>Что-то пошло не так</h2>
          <p style={{ marginBottom: 16, opacity: 0.7 }}>Мы уже видим ошибку и скоро её исправим.</p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Перезагрузить страницу</button>
        </div>
      </div>
    );
  }
}
