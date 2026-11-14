// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// Page-frame behaviour that has no markup of its own: analytics, scroll position (restored on back/forward), the
// phone viewport height, scrolling to the contact block after «Contact us» from the map.
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { initAnalytics, trackRoute } from '@/lib/analytics';
import { cancelRestore, enterEntry, restoreTop, setPageTop, watchViewport } from '@/lib/scroll';
import { showContact } from '@/lib/contact';

export default function RouteEffects() {
  const pathname = usePathname();

  useEffect(() => { initAnalytics(); return watchViewport(); }, []);

  // Every navigation.
  useEffect(() => {
    const revisit = enterEntry();
    cancelRestore();
    if (location.hash === '#contact') requestAnimationFrame(showContact);
    else if (revisit) restoreTop();
    else setPageTop(0);
    trackRoute();
  }, [pathname]);

  return null;
}
