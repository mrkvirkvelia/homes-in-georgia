// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// "Coming soon" page of a direction that has no offers yet (server component).
import Link from 'next/link';
import { Icon } from './Icon';
import { CHANNELS, CONTACT, GROUPS, SERVICES, telegramHref } from '@/lib/config';
import { translateList } from '@/lib/i18n';
import type { Fmt } from '@/lib/format';
import type { ServiceId } from '@/lib/types';

export default function Soon({ service, fmt, live }: { service: ServiceId; fmt: Fmt; live: ServiceId[] }) {
  const { t } = fmt;
  const svc = SERVICES[service];
  const channel = CHANNELS[service];
  return (
    <section className="soon">
      <div className="container">
        <nav className="crumbs"><Link href="/">{t('nav.home')}</Link><Icon name="right" /><span>{t('group.' + svc.group)}</span></nav>
        <div className="svc-tabs">{GROUPS[svc.group].services.map(s => (
          <Link key={s} className={`svc-tab${s === service ? ' on' : ''}`} href={`/${s}`}><Icon name={SERVICES[s].icon} />{t('svc.' + s + '.short')}{live.includes(s) ? '' : <sup>{t('svc.soon')}</sup>}</Link>
        ))}</div>
        <div className="soon-hero">
          <div>
            <span className="badge badge-accent"><Icon name="bell" />{t('soon.badge')}</span>
            <h1>{t('svc.' + service)}</h1>
            <p className="lead">{t('svc.' + service + '.desc')}. {t(channel ? 'soon.lead.channel' : 'soon.lead')}</p>
            <div className="soon-cta">
              <a className="btn btn-primary btn-lg" href={telegramHref(CONTACT.telegram)} target="_blank" rel="noopener" data-lead="telegram"><Icon name="send" /><span>{t('soon.cta')}</span></a>
              {channel && <a className="btn btn-outline btn-lg" href={telegramHref(channel)} target="_blank" rel="noopener">@{channel}</a>}
            </div>
          </div>
          <div className="soon-art" aria-hidden="true"><span><Icon name={svc.icon} /></span><i /><i /><i /></div>
        </div>
        <div className="soon-grid">
          <div className="soon-card">
            <h2>{t('soon.how')}</h2>
            <ol className="steps">{[1, 2, 3].map(n => <li key={n}><b>{n}</b><span>{t('soon.step.' + n)}</span></li>)}</ol>
          </div>
          <div className="soon-card">
            <h2>{t('soon.preview')}</h2>
            <div className="chips">{translateList(fmt.lang, 'soon.f.' + service).map(f => <span key={f} className="chip ghost"><Icon name="check" />{f}</span>)}</div>
          </div>
        </div>
        <h2 className="soon-more">{t('soon.meanwhile')}</h2>
        <div className="svc-grid">{live.map(s => (
          <Link key={s} className="svc-tile" href={`/${s}`}><span className="svc-ico"><Icon name={SERVICES[s].icon} /></span><span className="svc-name">{t('svc.' + s)}</span>
            <span className="svc-desc">{t('svc.' + s + '.desc')}</span><span className="svc-meta"><b></b><Icon name="arrow" /></span></Link>
        ))}</div>
      </div>
    </section>
  );
}
