"""
Вычистка секретов из данных ПЕРЕД сохранением на диск.

Зачем: Meta кладёт access_token в ссылки постраничной навигации (`paging.next`,
`paging.previous`), и они уезжают в сохранённый JSON вместе с ответом. 11.09.2026
в `data/ig_insights_2026-08-17.json` нашлось 7 таких токенов — файл просто лежал
в репозитории проекта. Обработчики ошибок мы уже починили (send_telegram.redact),
но там чинился только путь «ошибка → Telegram»; этот путь — «успешный ответ → диск».

Голый `EAA…` НЕ трогаем: такие фрагменты встречаются внутри CDN-ссылок Facebook
на фото (параметр `_nc_oc`), это не токены, и их порча ломает рабочие данные
(в Analytics_salebot/data/followup_state.json таких 17 тысяч записей).
"""

import re

_RX = [
    (re.compile(r"(access_token=)[^&\s\"'\\]+"), r"\1***"),
    (re.compile(r"(input_token=)[^&\s\"'\\]+"), r"\1***"),
    (re.compile(r"(client_secret=)[^&\s\"'\\]+"), r"\1***"),
    (re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{30,}"), "***:***"),  # токены Telegram-ботов
]


def scrub_text(s: str) -> str:
    for rx, repl in _RX:
        s = rx.sub(repl, s)
    return s


def scrub(obj):
    """Рекурсивно чистит строки в dict/list/tuple. Возвращает очищенную копию."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(scrub(v) for v in obj)
    return obj
