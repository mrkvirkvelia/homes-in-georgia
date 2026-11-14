// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// Local stand-in for the CRM public API (no deps): node scripts/mock-api.mjs  → http://127.0.0.1:8010
// Data: the old static site's listings.json (LISTINGS_JSON=path to override). Ids follow the CRM: "o<n>" rent / daily /
// commercial / new, "s<n>" sales, "c<n>" cars; the old id is kept as legacy_id and still resolves on /listings/{id}.
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';

const FILE = process.env.LISTINGS_JSON
  || '/private/tmp/claude-501/-Users-stnslv-Dev-Projects-rent-tbilisi-ai/0161008d-92ab-4f28-8451-1181909ff964/scratchpad/src/site/data/listings.json';
const PORT = +process.env.PORT || 8010;
const src = JSON.parse(readFileSync(FILE, 'utf8'));
const prefixOf = x => (x.kind === 'car' ? 'c' : x.service === 'sale' ? 's' : 'o');
const originals = new Map(); // "<id>/<n>" -> original photo path on hge.ge
const next = {};
const items = src.items.map(x => {
  const p = prefixOf(x);
  const id = `${p}${(next[p] = (next[p] || 0) + 1)}`;
  (x.photos || []).forEach((path, k) => originals.set(`${id}/${k + 1}`, path));
  return { ...x, id, legacy_id: x.id, updated_at: x.published_at,
    photos: (x.photos || []).map((_, k) => `/api/public/site/photos/${id}/${k + 1}`) };
});
const counts = {};
items.forEach(x => { counts[x.service] = (counts[x.service] || 0) + 1; });
const feed = { updated_at: new Date().toISOString(), rates_usd: src.rates_usd, counts, items };
const json = (res, code, body) => { res.writeHead(code, { 'content-type': 'application/json', 'cache-control': 'public, max-age=30' }); res.end(JSON.stringify(body)); };

createServer((req, res) => {
  const { pathname } = new URL(req.url, 'http://x');
  let m;
  if (pathname === '/api/public/site/listings') return json(res, 200, feed);
  if ((m = pathname.match(/^\/api\/public\/site\/listings\/([^/]+)$/))) {
    const id = decodeURIComponent(m[1]);
    const x = items.find(y => y.id === id || y.legacy_id === id);
    return x ? json(res, 200, { ...x, video: null }) : json(res, 404, { detail: 'not found' });
  }
  if ((m = pathname.match(/^\/api\/public\/site\/photos\/([a-z]\d+)\/(\d+)$/))) {
    const o = originals.get(`${m[1]}/${m[2]}`);
    if (!o) return json(res, 404, { detail: 'not found' });
    res.writeHead(302, { location: 'https://hge.ge/' + o });
    return res.end();
  }
  json(res, 404, { detail: 'not found' });
}).listen(PORT, '127.0.0.1', () => console.log(`mock api on http://127.0.0.1:${PORT} (${items.length} items)`));
