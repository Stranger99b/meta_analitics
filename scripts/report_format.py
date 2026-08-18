"""Единое форматирование отчётов для Telegram (HTML parse_mode).

Жирные заголовки секций + безопасное экранирование: контент (числа, подписи,
AI-текст) экранируется, а жирность расставляется через сентинелы, которые
экранирование не трогает. URL в наших отчётах без '&', поэтому безопасно.
"""
import html as _html

_BO = "\x01"  # bold open sentinel
_BC = "\x02"  # bold close sentinel


def b(text) -> str:
    """Пометить текст жирным (реальные теги проставит to_html)."""
    return f"{_BO}{text}{_BC}"


def to_html(s: str) -> str:
    s = _html.escape(s, quote=False)  # & < >
    return s.replace(_BO, "<b>").replace(_BC, "</b>")


def plain(s: str) -> str:
    """Убрать сентинелы жирности — для сохранения читаемого .txt."""
    return s.replace(_BO, "").replace(_BC, "")


_MDV2_SPECIAL = set(r"_*[]()~`>#+-=|{}.!\\")


def to_markdown(s: str) -> str:
    """MarkdownV2 для Telegram: экранируем спецсимволы, сентинелы → *жирный*."""
    out = []
    for ch in s:
        if ch in (_BO, _BC):
            out.append(ch)
        elif ch in _MDV2_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out).replace(_BO, "*").replace(_BC, "*")


def fmt(n) -> str:
    if n is None:
        return "—"
    return f"{n:,}".replace(",", " ")


def delta(cur, prev) -> str:
    """Тренд: '  ▲20%' / '  ▼5%' / '' — компактно, без скобок."""
    if cur is None or prev in (None, 0):
        return ""
    p = (cur - prev) / prev * 100
    if round(abs(p)) == 0:
        return "  ≈"
    return f"  {'▲' if p >= 0 else '▼'}{abs(p):.0f}%"


def line(label, cur, prev=None) -> str:
    """Строка метрики: 'Подписи — 12 345  ▲20%'."""
    return f"{label} — {fmt(cur)}{delta(cur, prev) if prev is not None else ''}"
