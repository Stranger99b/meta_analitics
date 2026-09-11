"""Единый AI-вывод для дайджестов: Qwen (--role) с фолбэком на Claude CLI.

Qwen экономит лимиты подписки; когда он недоступен (403 AccessDenied / лимит / пусто) —
фолбэк на `claude --print` (та же подписка Claude Code, без API-ключей). Возвращает
текст вывода или '' если оба источника недоступны — тогда дайджест выходит без AI-блока.
"""
import os
import shutil
import subprocess


def _qwen(instruction, summary, role, max_tokens, attempts, tag):
    qwen = shutil.which("qwen-ask") or "/home/user/.local/bin/qwen-ask"
    if not os.path.exists(qwen):
        return None
    cmd = [qwen, "--role", role]
    if max_tokens:
        cmd += ["--max-tokens", str(max_tokens)]
    cmd.append(instruction)
    for i in range(1, attempts + 1):
        try:
            r = subprocess.run(cmd, input=summary, capture_output=True,
                               text=True, timeout=200)
        except Exception as e:  # noqa: BLE001
            print(f"[{tag}] Qwen ошибка (попытка {i}): {e}")
            continue
        err = r.stderr or ""
        # Явные признаки недоступности Qwen — ретраить бессмысленно, сразу фолбэк
        if (r.returncode == 3 or "QWEN_QUOTA_EXCEEDED" in err
                or "AccessDenied" in err or "HTTP 403" in err):
            print(f"[{tag}] Qwen недоступен ({err.strip()[:80]}) — фолбэк на Claude")
            return None
        out = (r.stdout or "").strip()
        if out:
            print(f"[{tag}] AI-вывод получен от Qwen (попытка {i})")
            return out
        print(f"[{tag}] Ответ Qwen пуст/оборван (попытка {i}/{attempts})")
    return None


def _claude(instruction, summary, tag):
    claude = shutil.which("claude") or "/home/user/.local/bin/claude"
    if not os.path.exists(claude):
        print(f"[{tag}] claude CLI не найден — без AI-блока")
        return None
    prompt = f"{instruction}\n\n--- ДАННЫЕ ---\n{summary}"
    try:
        r = subprocess.run([claude, "--print"], input=prompt,
                           capture_output=True, text=True, timeout=300)
    except Exception as e:  # noqa: BLE001
        print(f"[{tag}] Claude fallback ошибка: {e}")
        return None
    out = (r.stdout or "").strip()
    if out:
        print(f"[{tag}] AI-вывод получен от Claude (fallback)")
        return out
    print(f"[{tag}] Claude fallback вернул пусто (код {r.returncode}): "
          f"{(r.stderr or '').strip()[:120]}")
    return None


def generate(instruction, summary, *, tag="ai", role="long",
             max_tokens=3000, qwen_attempts=2):
    """AI-текст для дайджеста: сначала Qwen, при недоступности — Claude. '' если оба легли."""
    out = _qwen(instruction, summary, role, max_tokens, qwen_attempts, tag)
    if out:
        return out
    return _claude(instruction, summary, tag) or ""
