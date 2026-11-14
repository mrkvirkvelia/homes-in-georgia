// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
// A page of the site. The server sends it as HTML (SEO, first paint); in the browser the ported page
// modules take over the same container: filters, sort, carousels, favourites, maps, share sheet.
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { mountPage, type PageKind, type Mounted } from '@/lib/mount';
import type { Item } from '@/lib/api';

interface Props { kind: PageKind; html: string; arg?: string; detail?: Item | null }

export default function LegacyView({ kind, html, arg = '', detail = null }: Props) {
  const [initial] = useState(html); // later server renders (new query) must not wipe what the browser built
  const ref = useRef<HTMLDivElement>(null);
  const page = useRef<Mounted | null>(null);
  const params = useSearchParams();
  const self = useRef<string | null>(params.toString()); // the query the page wrote itself (map filters)

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    let alive = true;
    const run = async () => {
      page.current?.destroy?.();
      page.current = null;
      const m = await mountPage(kind, root, {
        arg, detail, params: new URLSearchParams(location.search),
        onQuery: q => { self.current = q; },
      });
      if (alive) page.current = m; else m?.destroy?.();
    };
    run();
    // Language / currency changed in the header: draw the page again.
    const redraw = () => { run(); };
    addEventListener('hig:redraw', redraw);
    return () => { alive = false; removeEventListener('hig:redraw', redraw); page.current?.destroy?.(); page.current = null; };
  }, [kind, arg, detail]);

  // Address changed from outside (back/forward, a link with other filters).
  const query = params.toString();
  useEffect(() => {
    if (query === self.current) return;
    self.current = query;
    page.current?.update?.(new URLSearchParams(query));
  }, [query]);

  return <div className="view" ref={ref} tabIndex={-1} suppressHydrationWarning dangerouslySetInnerHTML={{ __html: initial }} />;
}
