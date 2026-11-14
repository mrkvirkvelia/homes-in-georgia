// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { Metadata, Viewport } from 'next';
import '@/styles/tokens.css';
import '@/styles/app.css';
import '@/styles/theme-dark.css';
import Providers from '@/components/Providers';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import TabBar from '@/components/TabBar';
import RouteEffects from '@/components/RouteEffects';
import { getRequest } from '@/lib/server';

export const metadata: Metadata = {
  metadataBase: new URL('https://hge.ge'),
  title: 'Homes in Georgia — homes, cars and investments in Georgia',
  description: 'Rentals and sales, new developments, daily stays and cars in Tbilisi. Live listings, smart filters and agents on Telegram.',
  authors: [{ name: 'Irakli Kvirkvelia · Homes in Georgia' }],
  icons: { icon: '/assets/img/favicon.svg' },
  openGraph: {
    type: 'website', siteName: 'Homes in Georgia', title: 'Homes in Georgia',
    description: 'Homes, cars and investments in Georgia — in one place.',
    images: ['/homes-in-georgia-splash.jpg'],
  },
};
export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover', themeColor: '#032D6A' };

// The saved theme is applied before the first paint, so a dark-theme visitor never sees a white flash.
const THEME = `try{if(localStorage.getItem('hig:theme')==='dark'){document.documentElement.dataset.theme='dark';document.querySelector('meta[name=theme-color]').content='#0B1220'}}catch(e){}`;

// The old site was one page with hash routes: /#/listing/rent-1 → /listing/rent-1, /#/rent?x=y → /rent?x=y, /#/map → /map.
const OLD_LINKS = `(function(){if(location.pathname!=='/')return;var h=location.hash;if(h.indexOf('#/')!==0)return;var p=h.slice(1);if(/^\\/(\\?|$)/.test(p)){history.replaceState(null,'',p==='/'?'/':p);return}location.replace(p)})()`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { lang, cur, feed, fmt, live } = await getRequest();
  return (
    <html lang={lang} suppressHydrationWarning>
      <head>
        {/* Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800;900&family=Noto+Sans+Georgian:wght@400;600;700&display=swap" rel="stylesheet" />
        <script dangerouslySetInnerHTML={{ __html: THEME + ';' + OLD_LINKS }} />
      </head>
      <body>
        <Providers lang={lang} cur={cur} rates={feed?.rates_usd ?? {}} live={live}>
          <Header />
          <div id="scroller" className="app-scroll">
            <main id="main" tabIndex={-1}>{children}</main>
            <Footer fmt={fmt} feed={feed} />
          </div>
          <TabBar />
          <noscript><p style={{ padding: 24 }}>Please enable JavaScript to use filters and the map on Homes in Georgia.</p></noscript>
          <RouteEffects />
        </Providers>
      </body>
    </html>
  );
}
