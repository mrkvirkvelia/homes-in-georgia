// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import LegacyView from '@/components/LegacyView';
import { loadRequest, applyRequest } from '@/lib/server';
import { homeMarkup } from '@/legacy/pages/home.js';
import { errorView } from '@/legacy/components.js';

// The old site was one page with hash routes: /#/listing/rent-1 → /listing/rent-1, /#/rent?x=y → /rent?x=y, /#/map → /map.
const OLD_LINKS = `(function(){var h=location.hash;if(h.indexOf('#/')!==0)return;var p=h.slice(1);if(/^\\/(\\?|$)/.test(p)){history.replaceState(null,'',p==='/'?'/':p);return}location.replace(p)})()`;

export default async function Home() {
  const r = await loadRequest();
  applyRequest(r);
  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: OLD_LINKS }} />
      <LegacyView kind="home" html={r.data ? homeMarkup(r.data) : errorView()} />
    </>
  );
}
