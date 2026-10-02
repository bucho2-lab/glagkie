#!/usr/bin/env python3
"""Разово поставить реакцию на посты канала с начала недели (понедельник, МСК).

Bot API не умеет читать историю канала, поэтому номера постов берутся
с публичной страницы https://t.me/s/<канал>. Запуск: workflow react-week.
"""
import datetime as dt, json, os, re
import requests
from bot import api, CHANNEL, REACTION, MSK

name = CHANNEL.lstrip("@")
html = requests.get(f"https://t.me/s/{name}", timeout=60).text
posts = re.findall(rf'data-post="{re.escape(name)}/(\d+)".*?<time datetime="([^"]+)"', html, re.S)
now = dt.datetime.now(MSK)
monday = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
done = failed = 0
for mid, when in posts:
    t = dt.datetime.fromisoformat(when).astimezone(MSK)
    if t < monday:
        continue
    try:
        api("setMessageReaction", chat_id=CHANNEL, message_id=mid,
            reaction=json.dumps([{"type": "emoji", "emoji": REACTION}]))
        print(f"OK  пост {mid} от {t:%d.%m %H:%M}")
        done += 1
    except Exception as e:
        print(f"ERR пост {mid} от {t:%d.%m %H:%M}: {e}")
        failed += 1
print(f"Всего постов на странице: {len(posts)}; с понедельника {monday:%d.%m}: реакция есть {done}, ошибок {failed}")
if failed:
    raise SystemExit(1)
