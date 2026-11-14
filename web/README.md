# hge.ge — public site (Next.js)

Next.js (App Router, TypeScript, `output: 'standalone'`) site: server components fetch the feed from the CRM and render
real content (titles, cards, prices, per-listing metadata); interactivity (filters, sorting, currency / language
switches, favourites, gallery, share sheet, maps) lives in client components. The design is the old CSS
(`src/styles/`, same class names). Data comes only from the CRM:

- `GET /api/public/site/listings` — feed `{updated_at, rates_usd, counts, items}` (`next: { revalidate: 60 }`)
- `GET /api/public/site/listings/{id}` — one listing, full description + video. `id` is `o<n>` (rent, daily, commercial, new), `s<n>` (sales), `c<n>` (cars) or an old id like `rent-551776`; 404 = not public

Photos are `/api/public/site/photos/<id>/<n>` (`?p=1` = 640 px preview: cards and maps use it, the gallery the full size). The browser loads photos (and, for saved listings, the feed) from the same domain.

## Layout

- `src/app/` — routes: `/`, `/[service]` (rent, sale, commercial, daily, new, car-rent, car-sale, all), `/listing/[id]`, `/map` (`?q=<address>` works), `/favorites`, `sitemap.ts`, `robots.ts`, `not-found.tsx`
- `src/components/` — `Providers` (language / currency, toasts, share sheet), page frame (`Header`, `Footer`, `TabBar`, `RouteEffects`), `ListingCard`, `Rail`, home (`Finder`, `RecentRail`), `Catalog` + `FilterSheet` + `CatalogMap`, listing page (`ListingParts`, `ListingSide`, `ShareSheet`), `MapApp`, `Favorites`, `Soon`
- `src/lib/` — `api.ts` / `server.ts` (server fetch, per-request language and currency), `format.ts` (translations, prices, dates: one `Fmt` object), `filters.ts` (filters ⇄ URL query), `i18n*.ts` (ru / en / ka), `config.ts`, `places.ts`, `favorites.ts`, `analytics.ts`, `scroll.ts`, `leaflet.ts` (Leaflet loaded from unpkg on demand)
- `scripts/mock-api.mjs` — local stand-in for the CRM API (no deps; ids `o…` / `s…` / `c…`)
- `/share/<id>.html` → 301 `/listing/<id>` (next.config); old `/#/...` links are redirected by a small script in the layout

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `API_URL` | `http://api:8000` | CRM API base for server-side fetches and the dev `/api/public/*` rewrite |

`API_URL` is read at runtime by the server fetches. The `rewrites()` proxy (dev only; in production Caddy takes `/api/public/*`) is evaluated at build time.

## Develop

```bash
cd web && npm ci
npm run mock                         # mock CRM API on :8010 (or run the real backend)
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

- The language is mirrored in the `hig_lang` cookie (currency: `hig_cur`), so the server renders the page in the visitor's language (else `Accept-Language`). Switching refreshes the server-rendered parts. Theme: `localStorage hig:theme`, applied before first paint.
- Filters, sort and map state live in the URL query (`/rent?price=-1500&beds=2`, `/map?from=rent&ch=sale`), so every state is a link.
- Favourites / recently viewed: `localStorage hig:fav` / `hig:recent` (old `rent-…` ids still match through `legacy_id`).
- Analytics (`ANALYTICS_URL` in `src/lib/config.ts`) is unchanged; reported page paths are real paths (`/listing/o123`, `/rent?...`) instead of `#/...`.
