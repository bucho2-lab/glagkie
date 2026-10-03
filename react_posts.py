#!/usr/bin/env python3
"""Проверить реакции бота на посты каналов за последние DAYS дней (по умолчанию 7)
и поставить недостающие. Реакция по номеру поста всегда одна и та же из карусели
REACTIONS, поэтому там, где она уже стоит, ничего не меняется.

Каналы — REACT_CHANNELS через запятую (по умолчанию только CHANNEL); бот должен
быть в них админом. Bot API не умеет читать историю канала, поэтому номера постов
берутся с публичной страницы https://t.me/s/<канал>. Запуск: workflow reactions,
каждые два часа.
"""
import datetime as dt, os, re
import requests
from bot import CHANNEL, MSK, react

channels = [c.strip() for c in os.environ.get("REACT_CHANNELS", CHANNEL).split(",") if c.strip()]
days = int(os.environ.get("DAYS", "7"))
since = dt.datetime.now(MSK) - dt.timedelta(days=days)
failed = 0
for channel in channels:
    name = channel.lstrip("@")
    try:
        html = requests.get(f"https://t.me/s/{name}", timeout=60).text
    except Exception as e:
        print(f"ERR {channel}: страница канала не открылась: {e}")
        failed += 1
        continue
    posts = re.findall(rf'data-post="{re.escape(name)}/(\d+)".*?<time datetime="([^"]+)"', html, re.S | re.I)
    done = 0
    for mid, when in posts:
        t = dt.datetime.fromisoformat(when).astimezone(MSK)
        if t < since:
            continue
        try:
            print(f"OK  {channel} пост {mid} от {t:%d.%m %H:%M}: {react(mid, channel)}")
            done += 1
        except Exception as e:
            print(f"ERR {channel} пост {mid} от {t:%d.%m %H:%M}: {e}")
            failed += 1
    print(f"{channel}: постов на странице {len(posts)}, за {days} дн. с реакцией {done}")
if failed:
    raise SystemExit(1)
