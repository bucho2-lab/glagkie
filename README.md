# Ролики «Свободное время»

Иван пишет боту @Gladkieliniibot дату и время (`30.09 11:00, 13:30 или 14:00, 18:00`), бот делает ролик
в стиле канала, присылает превью с кнопками «Опубликовать» / «Отменить» и по кнопке копирует его в @gladkie_linii_msk.

- `make_video.py` — ролик 720×1280, 12 с: фон из `assets/backgrounds`, музыка из `assets/music`,
  логотип `assets/logo.png`, шрифт Prata (`fonts/`). Фон, музыка и фраза меняются по дате.
  Чтобы добавить фон или трек, положите `.jpg` (720×1280) или `.m4a` в эти папки.
- `bot.py` — бот; `python bot.py` — один проход (GitHub Actions каждые 5 минут), `python bot.py --loop` — постоянно.

Секреты репозитория: `BOT_TOKEN`, `ADMIN_CHAT_ID`. Переменная (необязательно): `CHANNEL`.
Локально: `pip install -r requirements.txt && python make_video.py --date 2026-09-30 --slots 11:00 "13:30 или 14:00" -o test.mp4`.
