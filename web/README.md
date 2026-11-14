# hge.ge — public site (Next.js)

Next.js (App Router, TypeScript, `output: 'standalone'`) port of the old static site. The design is the old CSS
(`src/styles/`, same class names); the pages are server-rendered from the CRM API and the old modules take over in
the browser (filters, sort, carousels, favourites, maps, share sheet). Data comes only from the CRM:

- `GET /api/public/site/listings` — feed (`next: { revalidate: 60 }`)
- `GET /api/public/site/listings/{id}` — one listing (`o<pid>` or an old id like `rent-551776`), full description + video

Photos are `/api/public/site/photos/<pid>/<n>` (`?p=1` = 640 px preview). The browser loads the feed and photos from the same domain.

## Layout

- `src/app/` — routes: `/`, `/[service]` (rent, sale, commercial, daily, new, car-rent, car-sale, all), `/listing/[id]`, `/map` (`?q=<address>` works), `/favorites`, `sitemap.ts`, `robots.ts`, `not-found.tsx`
- `src/legacy/` — the old site's modules (config, i18n en/ka/ru, store, filters, map, share, analytics, page templates), ported as plain JS; not linted
- `src/components/` — `LegacyView` (hands a server-rendered page to its module in the browser), `Chrome` (header/footer behaviour, client links)
- `src/lib/` — `api.ts` (server fetch), `server.ts` (per-request language/currency), `mount.ts`
- `scripts/mock-api.mjs` — local stand-in for the CRM API (no deps)
- `/share/<id>.html` → 301 `/listing/<id>` (next.config); old `/#/...` links are redirected by a small script on `/`

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `API_URL` | `http://api:8000` | CRM API base for server-side fetches and the dev `/api/public/*` rewrite |

`API_URL` is read at runtime by the server fetches. The `rewrites()` proxy (dev only; in production Caddy takes `/api/public/*`) is evaluated at build time.

## Develop

```bash
cd web && npm ci
node scripts/mock-api.mjs            # mock CRM API on :8010 (or run the real backend)
API_URL=http://127.0.0.1:8010 npm run dev      # http://localhost:3000
npm run lint && npm run build
API_URL=http://127.0.0.1:8010 npm run start    # production build
```

Docker (from the repo root): `docker compose -f deploy/docker-compose.yml up -d --build web` — listens on `127.0.0.1:3000`.

## Caddy (production)

```
hge.ge {
    encode zstd gzip
    handle /api/public/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
www.hge.ge {
    redir https://hge.ge{uri} permanent
}
```

## Notes

- The language is chosen in the browser (`localStorage hig:lang`, else browser language) and mirrored in the `hig_lang` cookie (currency: `hig_cur`), so the server renders the page in the visitor's language. Theme: `hig:theme`.
- Analytics (`ANALYTICS_URL` in `src/legacy/config.js`) is unchanged; reported page paths are now real paths (`/listing/o123`, `/rent?...`) instead of `#/...`.
