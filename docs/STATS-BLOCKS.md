# «Статистика»: blocks of the old workbook → CRM (Stanislav 11-13, for David)

Source: `Rent In Tbilisi Form - Statistic .xlsx` (Google Sheets export, read 2026-11-13 with openpyxl, values + formulas).
Page: `/stats` (superadmins only), API: `GET /api/analytics/stats?month=YYYY-MM` (`backend/app/services/analytics.py: month_stats`).

## The workbook

56 sheets. Analytics live on two of them; everything else is the raw data they count:

| Sheet | What it is |
|---|---|
| **TBILISI ANALYSIS RENT AND SALE** | the current dashboard «Full statistics of the "Rent in Tbilisi🇬🇪" Platform since 11.11.2024», months Nov 24 … Oct 25 (the «10.25» analysis) |
| TBILISI Rent Analysis | the older version of the same dashboard, Nov 23 … Apr 25, typed numbers (no formulas) + 3 line charts of owners' / clients' prices |
| Supporting_pivot_table | Google pivot tables feeding the dashboard (Cash In by agent × month, rent-outs per month, rent-outs per agent, avg rental $/m² per agent) |
| Owner Traking System 2.0 / 1.0 | owners' objects (date, status, Rent/Sale, district, metro, rooms, price, m², price per m², agent, Month) |
| Clients Traking System, RENT Clients Information | clients (where from, Rent/Sale, status, budget «Цена $$», rooms, district, agent, Month) |
| Rent_out_Apartment | rent-outs = deals (price, agent, total commission, agent %, Month) |
| Tbilisi / Batumi Rent Agreement Data, Batumi *, SALE *, Day-Rent *, Ответы на форму (N), Лист* | form answers, contracts (passport data), Batumi and daily rent — no analytics on top of them |
| Sale Analysis, Analysis (web …), GPT | empty in the export |

Google-only functions (`COUNTUNIQUE`, pivot tables) were exported as cached values; several pivot ranges came out empty, so
the «Published» and «Rent Out» per-agent blocks are all zeros in the file (their charts were broken in the sheet as well).

## Blocks of «TBILISI ANALYSIS RENT AND SALE»

Rows are months (Nov 24 … Nov 25), columns are 21 agents (David, Sergi, Irakli, Alex, Dima, Danila, Zaza, Omari, Giga,
Semyon, Victoria, Shafi, Shorena, Arkadiy, Vitaly, Max, Artem, Giorgi, David Jr, Vlad, David2, Dasha) + Total.

| # | Block (rows) | Measures | Formula / source | Oct 25 in the file |
|---|---|---|---|---|
| 1 | **Published** (A94:W108) | objects published per agent per month | pivot over Owner Traking System 2.0 (status, Agent, Month) | 0 everywhere (pivot range lost in the export) |
| 1a | Published index (A109:L113) | month total; index vs Jan 25; sum of owners' prices; its index | `=W95…`, `=A110/C110`, `=Supporting_pivot_table!B106…`, `=A112/C112` | price sum **$220 175**, index 19.66 |
| 2 | **Client's** (A144:W159) | clients per agent per month | `=Supporting_pivot_table!O134…` (pivot over Clients Traking System: Agent × Month), `=SUM(B:V)` | **123** clients with one of the 21 agent columns (the column ↔ pivot-column links are shuffled, so per-agent numbers are unreliable) |
| 2a | Clients index (A161:L166) | month total; index vs Jan 25; sum of client budgets; its index; avg budget = sum / count | `=W145…`, `=A162/C162`, `=Supporting_pivot_table!B134…`, `=A164/A162` | budget sum **$174 615**; avg shown $1 148.78 (formula bug: `L164/J162` divides by Aug's count; correct 174 615 / 123 = $1 419.6, or / 386 all clients = $452) |
| 3 | Rent-outs per month (A205:J206) | rent-outs (COUNTA of IDs) per month | `=Supporting_pivot_table!B189…` (pivot over Rent_out_Apartment by Month) | filled only to Aug 25 (119); the pivot itself has **130** for 2025-10 |
| 4 | **Rent Out** (A209:X225) | rent-outs per agent per month | pivot (lost) | 0 everywhere |
| 5 | **Cash In** (A240:W259) | total commission per agent per month; agent % (B241: 0.5–0.9); Agent $$ = Total × %; Platform commission = Total − Agent; grand totals | `=Supporting_pivot_table!K99…`, `=B256*B241`, `=B256-B255`, `=SUM(B257:V257)` | pivot for 2025-10: David T. 16 300, Irakli 11 995, Viktoria 5 025, Semyon 3 610, Omari 3 465 … = **$62 432** (AP99). The dashboard row links some columns to the wrong pivot column (col «Vlad» shows Viktoria's 5 025, col «Zaza» Vitaly's 2 420). Since Nov 24: platform $68 511, agents $197 061 |
| 6 | **Cash In Agent** (A272:W286) | agent's share per month = Cash In × agent % | `=B253*B241` | David 14 670, Irakli 10 795.5, col «Vlad» 3 517.5 (= Viktoria × 0.7) … |
| 7 | **Summary / Quality** (A296:V304) | per agent: Published, Clients, Rent Out, Cash-in total, Cash-in agents; Published/Rent-out, Clients/Rent-out; **Quality** = average of the two ratios | `=B108`, `=SUM(B145:B153)`, `=B225`, `=B256`, `=B257`, `=B299/B297`, `=B299/B298`, `=AVERAGE(B302:B303)` | `#DIV/0!` (published/rent-out are 0); bar chart «Quality» |
| 8 | Rent-out totals (A325:Y327) | rent-outs per month, index vs Jan 25 | `=SUM(B210:V210)…`, `=A326/C326` | 0 / `#DIV/0!` |
| 9 | Chart «Average из Rental price per sq/m» | avg rental $/m² of each agent's objects | `Supporting_pivot_table!D513:X514` (AVERAGE of Owner Traking «Rental price per sq/m» by Agent) | David 11.17, Irakli 11.09, Alex 9.76, Victoria 20.79, Max 17.60, David Jr 29.98 … (all time) |

«TBILISI Rent Analysis» (old) has the same Published / Client's / Rent-Out / Cash-In / Quality blocks for Nov 23 – Apr 25
plus «Commission for 1 apartment» and totals via `COUNTUNIQUE` (owners 158, sum of prices $118 250, avg $748; clients 138,
$87 300, avg $633; rent-outs 26, $8 025, avg commission $309) — superseded by the sheet above, not rebuilt separately.

Raw-sheet facts for October 2025 (counted from the source sheets, Month = 2025-10):
owners **298** rows (276 Rent, 22 Sale; avg rental **$10.80/m²**; Saburtalo 113, Vake 51, Vera 32, Chugureti 29;
1 Bed 129, 2 Bed 109, Studio 24, 3 Bed 19) · clients **386** (budget sum $174 615; from Телеграмме 296, MyHome.ge|Ss.ge 83,
Рекомендация 4, Instagram 3; 139 without an agent) · rent-outs **130**, commission **$62 432**, avg rent $675.

## Mapping to the CRM

| Workbook block | CRM source (the month = Tbilisi calendar month) | Page block | Live? |
|---|---|---|---|
| 1 Published / 1a | `properties` added that month (`created_at`), avg `price`, avg `price/area`, `post_fields.deal = Sale` | KPI «Новых объектов», «Ср. цена объекта», agents table «Объекты», «$/м²» | live |
| 2 Client's / 2a | `leads` created that month (`created_ts`), per `agent_id`; budget = the «$N» in `leads.request` (N < 20 000 = rent budget) | KPI «Клиентов», «Ср. бюджет клиента» (avg over leads with a budget, not the sheet's buggy divisor), agents table «Клиенты» | live |
| 3 / 4 / 8 Rent Out | `deals` with `month = 'M/YYYY'`, status confirmed or pending (as the rest of the analytics) | KPI «Сдано квартир», agents «Сдано», 12-month chart/table | live |
| 5 Cash In / 6 Cash In Agent | `deals.commission_total`, `agent_amount`, `platform_amount` (the agent % is stored per deal by the calculator, not a fixed % per agent) | KPI «Комиссия», «Платформе / агентам», agents «Cash-in / Агенту / % / Платформе», chart «Cash-in по агентам» | live |
| 7 Quality | rent-outs / objects, rent-outs / clients, Quality = their average (per agent, the month) | agents table, last three columns | live |
| 9 $/m² per agent | avg `price/area` of the agent's objects added that month | agents table «$/м²» | live (per month, the sheet's was all-time) |
| index vs Jan 25 | replaced by % to the previous month | «±N% к прошлому» under the KPIs | live |
| Rent vs Sale | `deals.deal_type` | KPI «Продажи», rent line under the KPIs | live (sale deals only; **no sale-market data in the CRM**) |
| «Откуда пришел клиент» (Clients Traking col B) | old leads: «Откуда: …» in `leads.client_note`; new leads: `clients.channel` | «Откуда пришли клиенты» | live |
| — (owner sheet district/rooms) | `properties` district × `least(bedrooms, 4)`, median price, $/m² | «Цены аренды: район × спальни» → «Наши объекты» | live |
| — (market) | scraped feed `listings` (first_seen in the month), same grid | same card → «Рынок (парсер)» | live, but the feed starts 2026-11-10: earlier months show «Нет данных в CRM» |

Not rebuilt: sale-market analysis (the workbook's «Sale Analysis» is empty and the CRM scrapes rent only), Batumi and
day-rent sheets (separate businesses, no analytics in the workbook), the Rent Agreement form sheets (contracts data).

## October 2025: workbook vs CRM (prod, read-only, 2026-11-13)

| Number | Workbook | CRM | Why |
|---|---|---|---|
| Clients | 386 rows (123 under the 21 agent columns) | **386** leads (115 without agent) | same rows, imported by `importers/old_sheet.py`; the sheet's agent table only counted known agent columns |
| Client sources | Телеграмме 296, MyHome/Ss 83, Рекомендация 4, Instagram 3 | **identical** | |
| Client budget sum | $174 615 | $175 415 (avg $647 over 271 leads with a budget) | the importer takes «Цена $$» or, if empty, the sale price; one row differs |
| Rent-outs | 130 (Rent_out_Apartment) | **216** deals (206 rent + 10 sale) | the CRM also loaded the old CRM's `Reports_Deals` sheet (124 deals for 10/2025), merged with Rent_out by agent+price+object+month; 92 come from Rent_out_Apartment. 100 of the 216 have no agent linked |
| Cash-in | $62 432 | $88 286 (platform $10 231, agents $72 778) | same reason; agent shares in the CRM are per deal (calculator), not the sheet's fixed 50–90 % |
| Objects | 298 owner rows | 142 objects created in Oct 25 (avg $870, $11.28/m², 18 sale) | the importer merges a row into an earlier object of the same flat (cadastral / address) and keeps that object's older date, so ~half of October's rows count in earlier months |
| Prices by district | Saburtalo 113, Vake 51, Vera 32 rows | Saburtalo 48 (median $750), Vake 22 ($975), Vera 17 ($550) | same merge effect |

Follow-ups worth a look: link the 100 agent-less October 2025 deals (Reports_Deals rows) to agents; if David wants the
sheet's object counts, count `ai_flags.old_sheet` rows by their own date instead of the object's `created_at`.
