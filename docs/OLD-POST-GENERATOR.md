# Старый пост-генератор (post-generator-modern.html)

Источник: `PlatformDGE/-rentintbilisi-crm` → `post-generator-modern.html` (~1500 строк, статическая страница, шлёт в Telegram через Apps Script `gasRequest`). Два сценария: **Rent** и **Sale** (переключатель `setDeal`).

## Общие поля
Район (38 тегов), метро (22), адрес, ссылка на карту, заголовок («⭐️ … ⭐️» для аренды, «🌟 … 🌟» для продажи), эксклюзив (чекбокс → `❗️#Exclusive`), агент (тег `#Имя`, иначе `#???`), метраж, этаж/этажность («5/9»), фото и видео (сортировка, перемещение), собственник (имя, телефон).

## Аренда (`buildRentPost`)
- Тип: #Apartment / #House / #Commercial; спальни #1Bed–#4Bed; здание (#NewBuilding, #OldBuilding, #HistoricalBuilding, #Reconstruction); дизайн (#New #White #Grey #Yellow #Mixed #Old #Retro #UnderRepair); отопление (5); санузлы (#2–4Bathroom).
- Удобства (15): #Elevator #Oven #ParkingPlace #Conditioner — «фиксированные», остальные: #Balcony #Terrace #Courtyard #WiFi #TV #Bath #Shower #Dishwasher #Stove #Microwave #VacuumCleaner. Выбранные — `✅` по 3 в строке; невыбранные из фиксированных четырёх — `✖️` отдельной строкой.
- Жильцов (`👬Tenants: 1-N`), животные (#Allowed / #NotAllowed / #ByAgreement), сроки (#1Day #1Month #2Month #3Month #4Month #5Month #6Month #12Month).
- Цена: `💰 800$ + Deposit 800$`; залог по умолчанию = цене (метка «= цене / изменён»); всегда `0% Commission`.
- Авто-тег диапазона цены: до 300 / 300–500 / 500–700 / 700–900 / 900–1200 / 1200+ (`#Price0to300` … `#Price1200plus`).

## Продажа (`buildSalePost`)
- Тип (13): #Apartment #House #Land #Commercial #Retail #Business #Cafe #Restaurant #BeautySalon #Warehouses #Manufacture #Duplex #Townhouse; спальни #Studio, #1Bed–#5Bed, #6Bedplus.
- Состояние (#BlackFrame #WhiteFrame #GreenFrame #FullyRenovated), здание, дизайн (#NewApartment …), отопление, санузлы, положение этажа (`s-floorpos`).
- Удобства (12): #Balcony #Terrace #Courtyard #ParkingPlace #Conditioner #Dishwasher #Oven #Stove #Bath #Shower #Elevator #Fireplace (без ✖️).
- Цена с точками: `💰255.000$`; `0% Commission`; авто-тег диапазона из 24 ступеней (до 30 000 … до 1 000 000 и `#Price1000000plus`); в конце «SALE IN TBILISI🇬🇪».

## Шаблон поста (аренда)
```
#Vera 🚇 #Rustaveli
📍Адрес

⭐️ Заголовок ⭐️

❗️#Exclusive

🏢 #2Bed #Apartment for #Rent
✨ #NewBuilding | #White
🏠 65 sq.m | 5/9 Floor | #CentralHeating | #2Bathroom

✅ #Balcony  ✅ #WiFi  ✅ #Elevator
✖️ #Oven  ✖️ #ParkingPlace  ✖️ #Conditioner

👬Tenants: 1-3
🐕Pets: #ByAgreement
🕐 #12Month

💰 800$ + Deposit 800$
0% Commission
#Price700to900

📲 @David_Tibelashvili |
+995 599 20 67 16 #Agent

🌟 Check all listings | Reviews
📍APARTMENTS ON MAP📍
📱 Instagram 🗳 FB 🎥 YouTube
```
Продажа: «`for #Sale`», в строке стиля добавляется `| состояние`, в спецификации — положение этажа, без Tenants/Pets/периодов/залога.

## Публикация (`publishPost`) — всё в чат Advertising `-1003498137667`
1. **Топик 2 «оригиналы»:** каждое фото документом (без сжатия), видео, затем текст поста → из message_id строится ссылка `t.me/c/…`.
2. **Топик 207 «готовый пост»:** фото с водяным знаком (`applyWatermark`), у первого подпись (≤1024 символа), видео, текст.
3. **Топик 22 «Owner Information»** (если указан собственник): адрес, имя, телефон, ссылка на пост.
Дополнительно: «Скопировать», предпросмотр, сброс формы, подгрузка названий листов (`loadSheetNames`).

## В новой CRM
Аналог: `services/properties.py` (`post_text`, поля поста) и `notify.publish_post` (альбом с водяным знаком → `PUBLISH_TOPIC_ALBUM`, оригиналы → `PUBLISH_TOPIC_ORIGINALS`, контакт собственника + ссылка → `PUBLISH_TOPIC_OWNER`). Построчное сравнение шаблонов и списков тегов (район, метро, удобства, диапазоны цен, сроки, Sale-типы) я не делал — не проверено.
