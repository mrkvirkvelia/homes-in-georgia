// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Bottom bar of phones.
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Icon } from './Icon';
import ContactLink from './ContactLink';
import { useFmt } from './Providers';
import { useFavIds } from '@/lib/favorites';
import { isService } from '@/lib/config';

export default function TabBar() {
  const { t } = useFmt();
  const first = usePathname().split('/').filter(Boolean)[0] || '';
  const hasFavs = useFavIds().length > 0;
  const items: [string, string, string, boolean][] = [
    ['/', 'home', t('nav.home'), first === ''],
    ['/all', 'search', t('nav.search'), first === 'all' || isService(first)],
    ['/map', 'map', t('nav.map'), first === 'map'],
    ['/favorites', 'heart', t('nav.favorites'), first === 'favorites'],
  ];
  return (
    <nav id="tabbar" className="tabbar" aria-label="mobile">
      {items.map(([href, ic, label, on]) => (
        <Link key={href} href={href} className={on ? 'on' : ''} prefetch={false}>
          <Icon name={ic} /><span>{label}</span>{ic === 'heart' && hasFavs && <b className="dot" />}
        </Link>
      ))}
      <ContactLink><Icon name="send" /><span>{t('nav.contact')}</span></ContactLink>
    </nav>
  );
}
