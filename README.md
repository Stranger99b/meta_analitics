# GoTrips Analytics — Meta Ads · Instagram · Threads

Автоматическая аналитика для туристической компании **GoTrips** (@gotrips_by):
платная реклама Meta Ads **и** органика Instagram/Threads. Отчёты собираются по
расписанию и отправляются в Telegram — рекламные в личный чат, органические
(Instagram и Threads) — фирменным **PDF** в группу, тему «Отчет».

Данные берутся из Meta Marketing API, Instagram Graph API и Threads API;
качественные выводы генерирует ИИ (Qwen с фолбэком), вёрстка PDF — reportlab.

---

## Возможности

### 1. Meta Ads (платная реклама)
- **Ежедневный** отчёт (03:00): выгрузка за вчера, тренды, детектор выгорания
  креативов, AI-аудит → Telegram.
- **Еженедельный** отчёт (Пн 04:00): WoW-сравнение двух недель, стратегические выводы.
- Мониторинг подписчиков Instagram (снимок по дням).

### 2. Instagram — органика
- **Недельный** и **месячный** дайджесты в PDF: охваты, просмотры, вовлечённость,
  прирост подписчиков (WoW / MoM), топ публикаций с кликабельными ссылками, детектор
  «залетевшего» контента (≥2× среднего).
- **Аналитика сторис**: ежедневный снимок (API отдаёт только активные <24 ч),
  метрики просмотров/охвата/визитов профиля/подписок, **разбивка навигации**
  (вперёд/назад/закрыли/ушли) и метрика **удержания**. У каждой сторис — ID
  «дата #номер (время)» для поиска в архиве.
- **Сравнение типов контента** (рилс / посты / сторис) — что эффективнее и сколько
  какого контента нужно.
- Вся история сторис заливается в **Google Sheets** (ссылка в отчёте).

### 3. Threads — органика
- **Недельный** и **месячный** дайджесты в PDF в том же стиле: просмотры, лайки,
  ответы, репосты, цитирования, прирост подписчиков, топ постов со ссылками.

### Оценка работы SMM (в каждом дайджесте)
- **Прозрачная рубрика** (`smm_score.py`): балл 0–100 → 1–10 по 6 критериям — рост
  охвата/просмотров, вовлечённость (ER), прирост подписчиков, работа со сторис,
  активность (постинг), виральность. Гибрид норм и динамики; считается **кодом**
  (стабильно), выводится таблицей в PDF; критерии без данных исключаются.
- **Норматив SMM (KPI недели)** в конфиге `smm_score.py`: Reels 2, Карусели 1, Посты 1,
  Сторис 6/7 дней, Threads 4. В каждом дайджесте — блок **«План vs Факт»** (✓/✗), а балл
  за активность считается по МИКСУ (reels+карусели+посты отдельно) — алгоритм ловит именно
  нужные действия. Норматив продублирован в ресерч-плейбуке.
- **AI поясняет** рассчитанный балл (Qwen `--role long`, с ретраем/проверкой полноты
  и фолбэком) + рекомендации. Есть и в недельных, и в месячных, IG и Threads.

### Ресерч-плейбук роста
- `research_pdf.py` — фирменный PDF «Стратегия роста» для SMM (автобусные/групповые
  туры): диагноз аккаунта по реальным данным + тренды travel-SMM 2026 + контент-микс,
  пиллары, хуки, план. Разовый документ, запуск вручную.

### Фирменные PDF
- Салатовый бренд-цвет **#73D700** (с gotrips.by), цветные emoji (Twemoji),
  кликабельные ссылки на посты/рилс, таблицы для сторис и сравнения типов, номер
  недели/месяца в шапке и имени файла (напр. `№34_2026_IG_недельный_дайджест.pdf`),
  вёрстка под мобильный экран. Кириллица — DejaVuSans.

---

## Структура

```
meta_analitics/
├── scripts/
│   # --- Meta Ads ---
│   ├── fetch_meta_ads.py / fetch_meta_weekly.py
│   ├── analyze_campaigns.py / analyze_weekly.py
│   ├── creative_burnout.py / ai_audit.py / ig_followers.py
│   ├── run_daily.py / run_weekly.py
│   # --- Instagram органика ---
│   ├── fetch_ig_weekly.py / fetch_ig_monthly.py
│   ├── fetch_ig_stories_daily.py        # снимок сторис (3×/день)
│   ├── ig_content_compare.py            # сторис + сравнение типов
│   ├── analyze_ig_weekly.py / analyze_ig_monthly.py
│   ├── run_ig_weekly.py / run_ig_monthly.py
│   ├── stories_sheet.py                 # заливка сторис в Google Sheets
│   # --- Threads органика ---
│   ├── fetch_threads_weekly.py / fetch_threads_monthly.py
│   ├── analyze_threads_weekly.py / analyze_threads_monthly.py
│   ├── run_threads_weekly.py / run_threads_monthly.py
│   ├── exchange_threads_token.py
│   # --- Общее ---
│   ├── report_pdf.py                    # генерация PDF (reportlab)
│   ├── report_format.py                 # HTML-вёрстка/экранирование
│   ├── send_telegram.py                 # отправка текста/файлов/PDF
│   ├── exchange_token.py / update_token.py
│   └── assets/emoji/                    # Twemoji PNG для PDF
├── data/        # кэш, база сторис, архивы (не в git)
├── reports/     # архив отчётов и PDF (не в git)
├── .env         # токены и ID (не в git)
├── .env.example
└── requirements.txt
```

## Расписание (cron)

| Отчёт | Когда | Куда |
|---|---|---|
| Meta Ads дневной | 03:00 (резерв 07:00) | личный чат |
| Meta Ads недельный | Пн 04:00 | личный чат |
| Instagram недельный (PDF) | Пн 10:00 | группа, тема «Отчет» |
| Threads недельный (PDF) | Пн 10:05 | группа, тема «Отчет» |
| Instagram месячный (PDF) | 1-го, 10:15 | группа, тема «Отчет» |
| Threads месячный (PDF) | 1-го, 10:10 | группа, тема «Отчет» |
| Снимок сторис + Google Sheets | 07:00 / 15:00 / 23:00 | — |

Ручной запуск — тот же скрипт напрямую; месячные принимают аргумент `YYYY-MM`
для перегенерации за конкретный месяц.

## Настройка

Переменные в `.env` (см. `.env.example`):
- `META_ACCESS_TOKEN` — токен Meta (Instagram Graph + Ads), 60 дней; продлевается
  `exchange_token.py`. Права: `ads_read`, `business_management`, `instagram_basic`,
  `instagram_manage_insights`, `pages_read_engagement`, `pages_show_list`.
- `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` — отдельный токен Threads API
  (`exchange_threads_token.py`, права `threads_basic`, `threads_manage_insights`).
- `META_AD_ACCOUNT_ID`, `META_APP_ID`, `META_APP_SECRET`.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; `IG_TG_CHAT_ID`/`IG_TG_THREAD_ID` и
  `THREADS_TG_CHAT_ID`/`THREADS_TG_THREAD_ID` — группа и тема «Отчет».
- `GSHEETS_CREDENTIALS` — путь к service-account JSON (Google Sheets).

```
pip install -r requirements.txt
```

## Заметки
- Instagram Stories API отдаёт только активные сторис (<24 ч), поэтому нужен
  регулярный снимок; метрики растут все 24 ч → снимок 3×/день + dedup по макс.
  просмотрам.
- Instagram account insights ограничены окном 30 дней — месячные метрики собираются
  по частям и суммируются.
- Threads API отдельный от Facebook/Instagram (свой токен, база `graph.threads.net`).
