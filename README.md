# Ролики о свободных окнах

Иван пишет боту дату и время (`30.09 11:00, 14:30`), бот делает вертикальный ролик,
присылает превью с кнопками «Опубликовать» / «Отменить» и по кнопке копирует его в @gladkie_linii_msk.

- `make_video.py` — сборка ролика (1080×1920, 12 с).
- `bot.py` — бот; `python bot.py` — один проход (GitHub Actions каждые 5 минут), `python bot.py --loop` — постоянно (свой сервер).

Секреты репозитория: `BOT_TOKEN`, `ADMIN_CHAT_ID`. Переменные (необязательно): `CHANNEL`, `FOOTER`.
Локально: `pip install -r requirements.txt && python make_video.py --date 2026-09-30 --times 11:00 14:30 -o test.mp4`.
