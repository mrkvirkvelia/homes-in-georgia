// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Top bar: logo, direction menus, currency / language / theme switches, saved badge, contact button, mobile drawer.
import { Fragment, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Icon, Logo } from './Icon';
import ContactLink from './ContactLink';
import { useSite } from './Providers';
import { CONTACT, GROUPS, SERVICES, telegramHref, phoneHref, whatsappHref, type GroupId } from '@/lib/config';
import { LANGS } from '@/lib/i18n';
import { useFavIds } from '@/lib/favorites';
import { pageTop, scrollRoot } from '@/lib/scroll';
import { useDark } from '@/lib/hooks';

function MegaMenu({ group, onPick }: { group: GroupId; onPick?: () => void }) {
  const { fmt, live } = useSite();
  const { t } = fmt;
  return (
    <div className="mega" role="menu">
      {GROUPS[group].services.map(s => (
        <Link key={s} role="menuitem" href={`/${s}`} className="mega-item" onClick={onPick} prefetch={false}>
          <span className="svc-ico"><Icon name={SERVICES[s].icon} /></span>
          <span><b>{t('svc.' + s)}{live.includes(s) ? '' : <sup>{t('svc.soon')}</sup>}</b><small>{t('svc.' + s + '.desc')}</small></span>
        </Link>
      ))}
    </div>
  );
}

export default function Header() {
  const { fmt, setCur, setLang } = useSite();
  const { t, lang, cur } = fmt;
  const favs = useFavIds().length;
  const [scrolled, setScrolled] = useState(false);
  const [drop, setDrop] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);
  const dark = useDark();
  const lastScrollAt = useRef(0);
  // Every navigation closes the menus.
  const pathname = usePathname();
  const [seen, setSeen] = useState(pathname);
  if (seen !== pathname) { setSeen(pathname); setMenu(false); setDrop(null); }

  useEffect(() => {
    const target: HTMLElement | Window = scrollRoot() || window;
    const onScroll = () => setScrolled(pageTop() > 8);
    target.addEventListener('scroll', onScroll, { passive: true });
    // A tap that lands on a switch while the page is still scrolling must not trigger it.
    const stamp = () => { lastScrollAt.current = Date.now(); };
    document.addEventListener('scroll', stamp, { passive: true, capture: true });
    const outside = (e: MouseEvent) => { if (!(e.target as Element).closest('.nav-drop')) setDrop(null); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrop(null); };
    document.addEventListener('click', outside);
    document.addEventListener('keydown', esc);
    return () => {
      target.removeEventListener('scroll', onScroll);
      document.removeEventListener('scroll', stamp, { capture: true });
      document.removeEventListener('click', outside);
      document.removeEventListener('keydown', esc);
    };
  }, []);
  useEffect(() => { document.body.classList.toggle('menu-open', menu); return () => document.body.classList.remove('menu-open'); }, [menu]);

  const still = () => Date.now() - lastScrollAt.current < 400;
  const toggleTheme = () => {
    if (still()) return;
    const next = !dark;
    if (next) document.documentElement.dataset.theme = 'dark'; else delete document.documentElement.dataset.theme;
    document.querySelector('meta[name=theme-color]')?.setAttribute('content', next ? '#0B1220' : '#032D6A');
    try { localStorage.setItem('hig:theme', next ? 'dark' : 'light'); } catch { /* the choice just is not remembered */ }
  };
  const nextLang = LANGS[(LANGS.indexOf(lang) + 1) % LANGS.length];
  const themeLabel = t(dark ? 'nav.theme.light' : 'nav.theme.dark');

  return (
    <header id="header" className={`header${scrolled ? ' scrolled' : ''}`}>
      <div className="container nav">
        <Link className="brand" href="/" aria-label="Homes in Georgia"><Logo /></Link>
        <nav className="nav-main" aria-label="main">
          {(Object.keys(GROUPS) as GroupId[]).map(g => (
            <div key={g} className={`nav-drop${drop === g ? ' open' : ''}`}>
              <button type="button" className="nav-link" aria-haspopup="true" aria-expanded={drop === g} onClick={() => setDrop(drop === g ? null : g)}>{t('nav.' + g)}<Icon name="down" /></button>
              <MegaMenu group={g} onPick={() => setDrop(null)} />
            </div>
          ))}
          <Link className="nav-link nav-map" href="/map"><Icon name="map" />{t('nav.map')}</Link>
        </nav>
        <div className="nav-tools">
          <button type="button" className="hc hc-cur" aria-label={`${t('nav.currency')}: ${cur}`} title={t('nav.currency')}
            onClick={() => { if (!still()) setCur(cur === 'USD' ? 'GEL' : 'USD'); }}><b>{fmt.symbol}</b><small>{cur}</small></button>
          <button type="button" className="hc hc-lang" aria-label={`Language: ${lang.toUpperCase()}`} title="Language"
            onClick={() => { if (!still()) setLang(nextLang); }}><Icon name="globe" /><span lang={lang}>{lang.toUpperCase()}</span></button>
          <button type="button" className="icon-btn theme-btn" aria-label={themeLabel} title={themeLabel} onClick={toggleTheme}><Icon name={dark ? 'sun' : 'moon'} /></button>
          <Link className="icon-btn fav-link" href="/favorites" aria-label={t('nav.favorites')}><Icon name="heart" /><b className="nbadge">{favs || ''}</b></Link>
          <ContactLink className="btn btn-primary nav-cta"><Icon name="send" /><span>{t('nav.contact')}</span></ContactLink>
          <button type="button" className="icon-btn burger" aria-label={t('nav.menu')} aria-expanded={menu} onClick={() => setMenu(!menu)}><Icon name="menu" /></button>
        </div>
      </div>
      <div className="drawer" hidden={!menu}>
        <div className="container">
          {(Object.keys(GROUPS) as GroupId[]).map(g => <Fragment key={g}><p className="drawer-h">{t('group.' + g)}</p><MegaMenu group={g} onPick={() => setMenu(false)} /></Fragment>)}
          <div className="drawer-contact">
            <a className="btn btn-primary btn-block" href={telegramHref(CONTACT.telegram)} target="_blank" rel="noopener"><Icon name="send" /><span>Telegram</span></a>
            <a className="btn btn-outline btn-block" href={phoneHref()}><Icon name="phone" /><span>{CONTACT.phone}</span></a>
            <a className="btn btn-outline btn-block" href={whatsappHref()} target="_blank" rel="noopener"><Icon name="whatsapp" /><span>WhatsApp</span></a>
          </div>
        </div>
      </div>
    </header>
  );
}
