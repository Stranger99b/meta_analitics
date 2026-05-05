# Meta Ads Analytics — Gotrips

Автоматическая аналитика рекламных кампаний Meta Ads с ежедневным и еженедельным отчётом в Telegram + AI-аудит через Claude.

## Что делает система

- **Ежедневно в 3:00** — выгружает данные за вчера из Meta Marketing API, строит отчёт, запускает AI-аудит, отправляет в Telegram
- **Резерв в 7:00** — повторный запуск, если в 3:00 что-то пошло не так
- **Еженедельно в понедельник 4:00** — стратегический отчёт с WoW-сравнением двух недель

## Структура проекта

```
meta_analitics/
├── scripts/
│   ├── fetch_meta_ads.py      # Выгрузка данных из Meta API (с retry)
│   ├── fetch_meta_weekly.py   # Выгрузка данных за две недели
│   ├── analyze_campaigns.py   # Построение ежедневного отчёта
│   ├── analyze_weekly.py      # Построение еженедельного отчёта
│   ├── creative_burnout.py    # Детектор выгорания креативов
│   ├── ai_audit.py            # AI-аудит через Claude CLI
│   ├── ig_followers.py        # Мониторинг подписчиков Instagram
│   ├── send_telegram.py       # Отправка в Telegram
│   ├── run_daily.py           # Оркестратор ежедневного отчёта
│   ├── run_weekly.py          # Оркестратор еженедельного отчёта
│   └── update_token.py        # Обновление Meta Access Token
├── data/                      # Кэш данных (не в git)
├── reports/                   # Архив отчётов (не в git)
├── .env                       # Токены (не в git)
├── .env.example               # Шаблон переменных окружения
└── requirements.txt
```

## Метрики и стратегия

**Стратегия Gotrips (60/40):**
- **60% бюджета** → кампании "Диалог" — клиент пишет в директ → продажа. Ключевая метрика: диалоги, цена диалога (норма ≤ $3)
- **40% бюджета** → "Трафик в Профиль" — подписка → сторителлинг → отложенная продажа. Ключевые метрики: CTR, охват, сохранения

## Что входит в ежедневный отчёт

- Итого по аккаунту: расход, охват, CTR, CPC, CPM vs 7-дневный средний
- Количество диалогов и цена диалога
- Разбивка по кампаниям с трендами (↑↓→)
- Топ-5 адсетов по расходу
- Лучшие и худшие объявления по CTR
- **Детектор выгорания креативов**: сравнение CTR вчера vs 7д avg (🔴 критично / 🟡 внимание)
- Мониторинг подписчиков Instagram
- AI-аудит от Claude: диагноз, проблемы, конкретные действия на завтра

## Что входит в еженедельный отчёт

- Сравнение двух недель по всем метрикам с delta-стрелками
- Топ-6 адсетов, топ-4 и аутсайдеры объявлений
- Блок тенденций
- AI стратегический аудит: оценка недели, 3 инсайта, рекомендации на следующую неделю

## Установка

```bash
git clone https://github.com/Stranger99b/meta_analitics.git
cd meta_analitics
pip install -r requirements.txt
cp .env.example .env
# Заполнить .env своими токенами
```

### Переменные окружения (`.env`)

```
META_ACCESS_TOKEN=    # Долгоживущий токен Meta (60 дней), получить в Graph API Explorer
META_AD_ACCOUNT_ID=   # ID рекламного аккаунта (формат: act_XXXXXXXXX)
TELEGRAM_BOT_TOKEN=   # Токен Telegram-бота
TELEGRAM_CHAT_ID=     # ID чата для отправки отчётов
```

### Cron

```cron
0 3 * * * /usr/bin/python3 /path/to/meta_analitics/scripts/run_daily.py >> /path/to/data/cron.log 2>&1
0 7 * * * test -f /path/to/meta_analitics/reports/$(date +\%Y-\%m-\%d).txt || /usr/bin/python3 /path/to/meta_analitics/scripts/run_daily.py >> /path/to/data/cron.log 2>&1
0 4 * * 1 /usr/bin/python3 /path/to/meta_analitics/scripts/run_weekly.py >> /path/to/data/cron_weekly.log 2>&1
```

## Зависимости

- Python 3.8+
- `requests` — запросы к Meta API и Telegram
- `python-dotenv` — загрузка переменных окружения
- Claude CLI (`claude`) — для AI-аудита

## Обновление токена Meta

Токен Meta действует ~60 дней. Для обновления:

```bash
python3 scripts/update_token.py НОВЫЙ_ТОКЕН
```

Скрипт обновит `.env` и проверит валидность токена с датой истечения.
