// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Header, footer and mobile tab bar: HTML for the server and the browser, plus the browser behaviour
// (menus, language / currency / theme switches, «Contact us»). Ported from the old app.js.
import { t, getLang, setLang, languages, localeOf } from './i18n.js';
import { icon, logo } from './icons.js';
import { curChip, langChip } from './header-controls.js';
import { SERVICES, GROUPS, CONTACT, CHANNELS, SOCIALS, PORTALS, OFFICE_MAP, telegramHref, phoneHref, whatsappHref } from './config.js';
import { esc, serviceIcon } from './components.js';
import { favIds, getCurrency, setCurrency } from './store.js';
import { openShare, BRAND } from './share.js';
import { pageTop, scrollRoot } from './scroll.js';
import { go } from './nav.js';

// Light is the main theme; dark is opt-in from the header and remembered.
const isDark = () => typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark';
function setTheme(theme) {
  if (theme === 'dark') document.documentElement.dataset.theme = 'dark';
  else delete document.documentElement.dataset.theme;
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', theme === 'dark' ? '#0B1220' : '#032D6A');
  try { localStorage.setItem('hig:theme', theme); } catch { /* the choice just is not remembered */ }
}

function megaMenu(group) {
  return `<div class="mega" role="menu">
    ${GROUPS[group].services.map(s => `<a role="menuitem" href="/${s}" class="mega-item">
      <span class="svc-ico">${icon(serviceIcon(s))}</span>
      <span><b>${t('svc.' + s)}${SERVICES[s].live ? '' : `<sup>${t('svc.soon')}</sup>`}</b><small>${t('svc.' + s + '.desc')}</small></span>
    </a>`).join('')}
  </div>`;
}

export function headerMarkup() {
  const favs = favIds().length;
  return `
  <div class="container nav">
    <a class="brand" href="/" aria-label="Homes in Georgia">${logo()}</a>
    <nav class="nav-main" aria-label="main">
      ${Object.keys(GROUPS).map(g => `<div class="nav-drop"><button type="button" class="nav-link" aria-haspopup="true" aria-expanded="false">${t('nav.' + g)}${icon('down')}</button>${megaMenu(g)}</div>`).join('')}
      <a class="nav-link nav-map" href="/map">${icon('map')}${t('nav.map')}</a>
    </nav>
    <div class="nav-tools">
      ${curChip()}
      ${langChip()}
      <button type="button" class="icon-btn theme-btn" data-theme-toggle aria-label="${esc(t(isDark() ? 'nav.theme.light' : 'nav.theme.dark'))}" title="${esc(t(isDark() ? 'nav.theme.light' : 'nav.theme.dark'))}">${icon(isDark() ? 'sun' : 'moon')}</button>
      <a class="icon-btn fav-link" href="/favorites" aria-label="${esc(t('nav.favorites'))}">${icon('heart')}<b class="nbadge">${favs || ''}</b></a>
      <a class="btn btn-primary nav-cta" href="#contact" data-contact>${icon('send')}<span>${t('nav.contact')}</span></a>
      <button type="button" class="icon-btn burger" aria-label="${esc(t('nav.menu'))}" aria-expanded="false">${icon('menu')}</button>
    </div>
  </div>
  <div class="drawer" hidden>
    <div class="container">
      ${Object.keys(GROUPS).map(g => `<p class="drawer-h">${t('group.' + g)}</p>${megaMenu(g)}`).join('')}
      <div class="drawer-contact">
        <a class="btn btn-primary btn-block" href="${telegramHref(CONTACT.telegram)}" target="_blank" rel="noopener">${icon('send')}<span>Telegram</span></a>
        <a class="btn btn-outline btn-block" href="${phoneHref()}">${icon('phone')}<span>${esc(CONTACT.phone)}</span></a>
        <a class="btn btn-outline btn-block" href="${whatsappHref()}" target="_blank" rel="noopener">${icon('whatsapp')}<span>WhatsApp</span></a>
      </div>
    </div>
  </div>`;
}

function rateLine(data) {
  const r = data?.rates_usd;
  if (!r || data.rates_source !== 'NBG') return '';
  const fmt = v => v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
  const date = data.rates_date ? new Date(data.rates_date).toLocaleDateString(localeOf()) : '';
  return '<br>' + esc(t('footer.rates', date, fmt(1 / r.GEL), fmt(r.EUR / r.GEL)));
}

const brandMark = name => BRAND[name] ? `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${BRAND[name]}</svg>` : icon(name === 'tel' ? 'phone' : name);
const footRow = (href, mark, title, sub, external = true) => `<a class="foot-row" href="${esc(href)}"${external ? ' target="_blank" rel="noopener"' : ''}><span class="foot-mark foot-mark-${mark}">${brandMark(mark)}</span><span><b>${esc(title)}</b><small>${esc(sub)}</small></span></a>`;
// One social account: a glass circle with the white logo and a short caption under it.
const socIcon = (brand, a) => {
  const full = `${brand} · ${a.name} ${a.handle}`;
  return `<a class="soc" href="${esc(a.href)}" target="_blank" rel="noopener" title="${esc(full)}" aria-label="${esc(full)}" data-social="${esc(`${a.name.toLowerCase()} ${a.handle}`)}"><span class="soc-i">${brandMark(a.icon)}</span><span class="soc-l">${esc(t(a.label))}</span></a>`;
};
const footChip = (href, mark, name, sub) => `<a class="foot-chip" href="${esc(href)}" target="_blank" rel="noopener"><span class="foot-mark">${brandMark(mark)}</span><span><b>${esc(name)}</b><small>${esc(sub)}</small></span></a>`;

export function footerMarkup(data) {
  return `
  <div class="container foot">
    <div class="foot-brand">${logo('logo-light')}<p>${t('footer.about')}</p></div>
    ${Object.keys(GROUPS).map(g => `<div><h4>${t('group.' + g)}</h4>${GROUPS[g].services.map(s => `<a href="/${s}">${t('svc.' + s)}</a>`).join('')}</div>`).join('')}
    <div><details class="foot-channels"><summary>${t('footer.channels')}${icon('down')}</summary>${Object.entries(CHANNELS).map(([s, c]) => `<a href="${telegramHref(c)}" target="_blank" rel="noopener" title="${esc(t('svc.' + s))}">@${c}</a>`).join('')}</details></div>
  </div>
  <div class="container foot-connect">
    <section id="contact"><h4>${t('footer.contact')}</h4><div class="foot-rows">
      ${footRow(phoneHref(), 'tel', t('footer.call'), CONTACT.phone, false)}
      ${footRow(whatsappHref(), 'whatsapp', t('footer.whatsapp'), CONTACT.phone)}
      ${footRow(telegramHref(), 'telegram', t('footer.telegram'), t('footer.message'))}
      ${footRow(OFFICE_MAP, 'pin', t('footer.office'), t('footer.address'))}
    </div></section>
    <section class="foot-social"><h4>${t('footer.social')}</h4>
      ${SOCIALS.map(g => `<div class="soc-group"><p class="soc-brand">${esc(g.brand)}</p><div class="soc-row">${g.accounts.map(a => socIcon(g.brand, a)).join('')}</div></div>`).join('')}
    </section>
    <section><h4>${t('footer.listings')}</h4><div class="foot-chips">
      ${PORTALS.map(p => footChip(p.href, 'list', p.name, t('footer.allads'))).join('')}
    </div></section>
  </div>
  <div class="container foot-bottom"><span>© ${new Date().getFullYear()} Homes in Georgia. ${t('footer.rights')}</span><span>${t('footer.data')}${rateLine(data)}</span></div>`;
}

/** `first` is the first path segment of the current page ('' = home). */
export function tabbarMarkup(first) {
  const items = [['/', 'home', t('nav.home'), first === ''], ['/all', 'search', t('nav.search'), first === 'all' || !!SERVICES[first]],
    ['/map', 'map', t('nav.map'), first === 'map'],
    ['/favorites', 'heart', t('nav.favorites'), first === 'favorites'], ['#contact', 'send', t('nav.contact'), false]];
  return items.map(([href, ic, label, on]) =>
    `<a href="${href}"${href === '#contact' ? ' data-contact' : ''} class="${on ? 'on' : ''}">${icon(ic)}<span>${esc(label)}</span>${ic === 'heart' && favIds().length ? '<b class="dot"></b>' : ''}</a>`).join('');
}

// «Contact us» leads to the contact block at the bottom of the page.
// The full-screen map has no footer, so from there it goes through the home page.
let contactAfterRoute = false;
export function showContact() {
  // Lists below may still grow while the page settles, so aim again a few times.
  const aim = () => document.getElementById('contact')?.scrollIntoView({ behavior: 'auto', block: 'start' });
  aim();
  [120, 300, 600].forEach(ms => setTimeout(aim, ms));
}
/** Called after every route change: scrolls to the contact block when «Contact us» was pressed on the map. */
export function afterRoute() {
  if (!contactAfterRoute) return false;
  contactAfterRoute = false;
  requestAnimationFrame(showContact);
  return true;
}

/**
 * Browser behaviour of the three blocks. `redraw()` re-renders them and the current page
 * (after a language or currency change); `data()` returns the feed once loaded.
 */
export function installShell({ header, redraw, redrawHeader, data }) {
  // A tap that lands on the moon while the page is scrolling must not switch the theme.
  let lastScrollAt = 0;
  document.addEventListener('scroll', () => { lastScrollAt = Date.now(); }, { passive: true, capture: true });
  const stillScrolling = () => Date.now() - lastScrollAt < 400;

  header.addEventListener('click', e => {
    if (e.target.closest('[data-cur-toggle]')) { if (stillScrolling()) return; setCurrency(getCurrency() === 'USD' ? 'GEL' : 'USD'); redraw(); return; }
    if (e.target.closest('[data-theme-toggle]')) { if (stillScrolling()) return; setTheme(isDark() ? 'light' : 'dark'); redrawHeader(); return; }
    const langBtn = e.target.closest('[data-lang]');
    if (langBtn) {
      if (langBtn.dataset.lang === getLang() || stillScrolling()) return;
      // Slide the glass thumb first, then re-render in the new language.
      langBtn.parentElement.style.setProperty('--i', languages.indexOf(langBtn.dataset.lang));
      setLang(langBtn.dataset.lang);
      setTimeout(redraw, 180);
      return;
    }
    const burger = e.target.closest('.burger');
    if (burger) {
      const drawer = header.querySelector('.drawer');
      const open = drawer.hasAttribute('hidden');
      drawer.toggleAttribute('hidden', !open);
      burger.setAttribute('aria-expanded', open);
      document.body.classList.toggle('menu-open', open);
      return;
    }
    const drop = e.target.closest('.nav-link');
    if (drop && drop.parentElement.classList.contains('nav-drop')) {
      const wrap = drop.parentElement;
      const open = !wrap.classList.contains('open');
      header.querySelectorAll('.nav-drop').forEach(d => { d.classList.remove('open'); d.querySelector('.nav-link').setAttribute('aria-expanded', 'false'); });
      wrap.classList.toggle('open', open);
      drop.setAttribute('aria-expanded', open);
      return;
    }
    if (e.target.closest('.mega-item')) header.querySelectorAll('.nav-drop').forEach(d => d.classList.remove('open'));
  });
  document.addEventListener('click', e => {
    if (e.target.closest('[data-contact]')) {
      e.preventDefault();
      if (document.body.classList.contains('map-page')) {
        contactAfterRoute = true;
        go('/');
      } else {
        showContact();
      }
      return;
    }
    const share = e.target.closest('[data-share-id]');
    if (share && data()) {
      e.preventDefault();
      const item = data().byId.get(share.dataset.shareId);
      if (item) openShare(item);
      return;
    }
    if (!e.target.closest('.nav-drop')) header.querySelectorAll('.nav-drop.open').forEach(d => d.classList.remove('open'));
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') header.querySelectorAll('.nav-drop.open').forEach(d => d.classList.remove('open'));
  });
  (scrollRoot() || window).addEventListener('scroll', () => header.classList.toggle('scrolled', pageTop() > 8), { passive: true });
}
