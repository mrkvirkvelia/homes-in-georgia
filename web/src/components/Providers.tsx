// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// What every client component of the site shares: language and currency (the visitor's switches), the live
// directions, toasts and the share sheet. The server renders the first values from the cookies hig_lang / hig_cur.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createFmt, type Fmt } from '@/lib/format';
import ShareSheet from './ShareSheet';
import type { Cur, Item, Lang, ServiceId } from '@/lib/types';

interface Site {
  fmt: Fmt;
  live: ServiceId[];
  setLang: (lang: Lang) => void;
  setCur: (cur: Cur) => void;
  notify: (text: string) => void;
  share: (x: Item) => void;
}
const SiteContext = createContext<Site | null>(null);

export const useSite = (): Site => {
  const site = useContext(SiteContext);
  if (!site) throw new Error('useSite outside <Providers>');
  return site;
};
export const useFmt = () => useSite().fmt;

const YEAR = 31536000;
const remember = (key: 'lang' | 'cur', value: string) => {
  try { localStorage.setItem('hig:' + (key === 'lang' ? 'lang' : 'cur'), key === 'cur' ? JSON.stringify(value) : value); } catch { /* not remembered */ }
  // The server reads these cookies to render the page in the visitor's language and currency.
  document.cookie = `hig_${key}=${value};path=/;max-age=${YEAR};samesite=lax`;
};

interface Props { lang: Lang; cur: Cur; rates: Record<string, number>; live: ServiceId[]; children: React.ReactNode }

export default function Providers({ lang: initialLang, cur: initialCur, rates, live, children }: Props) {
  const router = useRouter();
  const [lang, setLangState] = useState(initialLang);
  const [cur, setCurState] = useState(initialCur);
  const [toast, setToast] = useState({ text: '', show: false });
  const [sharing, setSharing] = useState<Item | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const fmt = useMemo(() => createFmt(lang, cur, rates), [lang, cur, rates]);
  // Server pieces (header, listing page…) are drawn again with the new cookie; client pieces switch at once.
  const setLang = useCallback((next: Lang) => {
    remember('lang', next);
    document.documentElement.lang = next;
    setLangState(next);
    router.refresh();
  }, [router]);
  const setCur = useCallback((next: Cur) => {
    remember('cur', next);
    setCurState(next);
    router.refresh();
  }, [router]);
  const notify = useCallback((text: string) => {
    clearTimeout(timer.current);
    setToast({ text, show: true });
    timer.current = setTimeout(() => setToast(s => ({ ...s, show: false })), 2200);
  }, []);
  const share = useCallback((x: Item) => setSharing(x), []);
  useEffect(() => () => clearTimeout(timer.current), []);

  const site = useMemo(() => ({ fmt, live, setLang, setCur, notify, share }), [fmt, live, setLang, setCur, notify, share]);
  return (
    <SiteContext.Provider value={site}>
      {children}
      {sharing && <ShareSheet item={sharing} onClose={() => setSharing(null)} />}
      <div className={`toast${toast.show ? ' show' : ''}`} role="status">{toast.text}</div>
    </SiteContext.Provider>
  );
}
