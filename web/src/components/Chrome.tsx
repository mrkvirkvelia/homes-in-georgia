// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Browser behaviour of the page frame: header menus, language / currency / theme switches, client-side links,
// favourites badge, scroll restoration, analytics. The frame itself (header, footer, tab bar) is server HTML.
import { useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { setRouter } from '@/legacy/nav.js';
import { initLang } from '@/legacy/i18n.js';
import { installInteractions } from '@/legacy/components.js';
import { onFavChange } from '@/legacy/store.js';
import { headerMarkup, footerMarkup, tabbarMarkup, installShell, afterRoute } from '@/legacy/shell.js';
import { enterEntry, setPageTop, restoreTop, cancelRestore } from '@/legacy/scroll.js';
import { initAnalytics, trackRoute } from '@/legacy/analytics.js';
import { getFeed } from '@/lib/mount';
import type { Feed } from '@/lib/api';

const $ = (id: string) => document.getElementById(id)!;
const firstSegment = () => location.pathname.split('/').filter(Boolean)[0] || '';

export default function Chrome() {
  const router = useRouter();
  const pathname = usePathname();
  const feed = useRef<Feed | null>(null);

  // Once per page load.
  useEffect(() => {
    setRouter(router);
    initLang();
    const drawFrame = () => {
      $('header').innerHTML = headerMarkup();
      $('footer').innerHTML = footerMarkup(feed.current);
      $('tabbar').innerHTML = tabbarMarkup(firstSegment());
    };
    const redrawHeader = () => { $('header').innerHTML = headerMarkup(); };
    // Language or currency changed: frame and page are drawn again.
    const redraw = () => { drawFrame(); dispatchEvent(new Event('hig:redraw')); };
    drawFrame();
    getFeed().then(d => { feed.current = d; drawFrame(); }).catch(() => {});
    installInteractions();
    installShell({ header: $('header'), redraw, redrawHeader, data: () => feed.current });
    initAnalytics();
    onFavChange((n: number) => {
      const badge = $('header').querySelector('.fav-link .nbadge');
      if (badge) badge.textContent = n ? String(n) : '';
      $('tabbar').innerHTML = tabbarMarkup(firstSegment());
    });
    // Internal links move through the Next router (no full reload); the page keeps its feed in memory.
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element).closest?.('a[href]');
      if (!a || (a.getAttribute('target') && a.getAttribute('target') !== '_self') || a.hasAttribute('download')) return;
      const href = a.getAttribute('href') || '';
      if (!href.startsWith('/') || href.startsWith('//') || href.startsWith('/api/')) return;
      e.preventDefault();
      router.push(href);
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Every navigation.
  useEffect(() => {
    document.querySelectorAll('.sheet-wrap, .lightbox').forEach(el => el.remove());
    document.body.classList.remove('locked', 'menu-open');
    $('header').querySelector('.drawer')?.setAttribute('hidden', '');
    $('tabbar').innerHTML = tabbarMarkup(firstSegment());
    const revisit = enterEntry();
    cancelRestore();
    if (afterRoute()) { /* scrolling to the contact block */ } else if (revisit) restoreTop(); else setPageTop(0);
    trackRoute();
  }, [pathname]);

  return null;
}
