#!/usr/bin/env python3
"""Проверить реакции бота на посты канала за последние DAYS дней (по умолчанию 7)
и поставить недостающие. Реакция по номеру поста всегда одна и та же из карусели
REACTIONS, поэтому там, где она уже стоит, ничего не меняется.

Bot API не умеет читать историю канала, поэтому номера постов берутся
с публичной страницы https://t.me/s/<канал>. Запуск: workflow reactions,
каждые два часа.
"""
import datetime as dt, os, re
import requests
from bot import CHANNEL, MSK, react

name = CHANNEL.lstrip("@")
days = int(os.environ.get("DAYS", "7"))
html = requests.get(f"https://t.me/s/{name}", timeout=60).text
posts = re.findall(rf'data-post="{re.escape(name)}/(\d+)".*?<time datetime="([^"]+)"', html, re.S)
since = dt.datetime.now(MSK) - dt.timedelta(days=days)
done = failed = 0
for mid, when in posts:
    t = dt.datetime.fromisoformat(when).astimezone(MSK)
    if t < since:
        continue
    try:
        print(f"OK  пост {mid} от {t:%d.%m %H:%M}: {react(mid)}")
        done += 1
    except Exception as e:
        print(f"ERR пост {mid} от {t:%d.%m %H:%M}: {e}")
        failed += 1
print(f"Постов на странице: {len(posts)}; за {days} дн.: с реакцией {done}, ошибок {failed}")
if failed:
    raise SystemExit(1)
