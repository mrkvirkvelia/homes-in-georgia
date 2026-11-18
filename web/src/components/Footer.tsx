// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Footer of every page (server component): directions, channels, contacts, social accounts, portals, NBG rate.
import Link from 'next/link';
import { Icon, BrandMark, Logo } from './Icon';
import { localeOf } from '@/lib/i18n';
import { CHANNELS, CONTACT, GROUPS, OFFICE_MAP, SOCIALS, phoneHref, telegramHref, whatsappHref, type GroupId } from '@/lib/config';
import type { Fmt } from '@/lib/format';
import type { Feed, ServiceId } from '@/lib/types';

function FootRow({ href, mark, title, sub, external = true }: { href: string; mark: string; title: string; sub: string; external?: boolean }) {
  return (
    <a className="foot-row" href={href} {...(external ? { target: '_blank', rel: 'noopener' } : {})}>
      <span className={`foot-mark foot-mark-${mark}`}><BrandMark name={mark} /></span><span><b>{title}</b><small>{sub}</small></span>
    </a>
  );
}

function RateLine({ feed, fmt }: { feed: Feed | null; fmt: Fmt }) {
  const r = feed?.rates_usd;
  if (!feed || !r || feed.rates_source !== 'NBG') return null;
  const f = (v: number) => v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
  const date = feed.rates_date ? new Date(feed.rates_date).toLocaleDateString(localeOf(fmt.lang)) : '';
  return <><br />{fmt.t('footer.rates', date, f(1 / r.GEL), f(r.EUR / r.GEL))}</>;
}

export default function Footer({ fmt, feed }: { fmt: Fmt; feed: Feed | null }) {
  const { t } = fmt;
  return (
    <footer id="footer" className="footer">
      <div className="container foot">
        <div className="foot-brand"><Logo className="logo-light" /><p>{t('footer.about')}</p></div>
        {(Object.keys(GROUPS) as GroupId[]).map(g => (
          <div key={g}><h4>{t('group.' + g)}</h4>{GROUPS[g].services.map(s => <Link key={s} href={`/${s}`} prefetch={false}>{t('svc.' + s)}</Link>)}</div>
        ))}
        <div><details className="foot-channels"><summary>{t('footer.channels')}<Icon name="down" /></summary>
          {(Object.entries(CHANNELS) as [ServiceId, string][]).map(([s, c]) => <a key={s} href={telegramHref(c)} target="_blank" rel="noopener" title={t('svc.' + s)}>@{c}</a>)}
        </details></div>
      </div>
      <div className="container foot-connect">
        <section id="contact"><h4>{t('footer.contact')}</h4><div className="foot-rows">
          <FootRow href={phoneHref()} mark="tel" title={t('footer.call')} sub={CONTACT.phone} external={false} />
          <FootRow href={whatsappHref()} mark="whatsapp" title={t('footer.whatsapp')} sub={CONTACT.phone} />
          <FootRow href={telegramHref()} mark="telegram" title={t('footer.telegram')} sub={t('footer.message')} />
          <FootRow href={OFFICE_MAP} mark="pin" title={t('footer.office')} sub={t('footer.address')} />
        </div></section>
        <section className="foot-social"><h4>{t('footer.social')}</h4>
          {SOCIALS.map(g => (
            <div key={g.brand} className="soc-group"><p className="soc-brand">{g.brand}</p><div className="soc-row">
              {g.accounts.map(a => {
                const full = `${g.brand} · ${a.name} ${a.handle}`;
                return (
                  <a key={a.href} className="soc" href={a.href} target="_blank" rel="noopener" title={full} aria-label={full} data-social={`${a.name.toLowerCase()} ${a.handle}`}>
                    <span className="soc-i"><BrandMark name={a.icon} /></span><span className="soc-l">{t(a.label)}</span>
                  </a>
                );
              })}
            </div></div>
          ))}
        </section>
      </div>
      <div className="container foot-bottom"><span>© {new Date().getFullYear()} Homes in Georgia. {t('footer.rights')}</span><span>{t('footer.data')}<RateLine feed={feed} fmt={fmt} /></span></div>
    </footer>
  );
}
