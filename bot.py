#!/usr/bin/env python3
"""Telegram-бот: дата и время свободных окон -> ролик -> превью -> публикация в канал.

Переменные окружения:
  BOT_TOKEN      токен от @BotFather (секрет)
  ADMIN_CHAT_ID  id чата Ивана; только ему бот отвечает и присылает превью
  CHANNEL        канал для публикации, по умолчанию @gladkie_linii_msk
  REACTIONS      реакции бота на посты канала по очереди, по умолчанию 🔥,❤,👍

Режимы:
  python3 bot.py              один проход по новым сообщениям
  python3 bot.py --loop       работать постоянно (для своего сервера)
  python3 bot.py --loop 1500  слушать 25 минут (так запускает GitHub Actions)
  python3 bot.py --ask-templates  попросить новые картинки (по воскресеньям)

Картинки, которые Иван присылает боту, сохраняются в assets/templates/<воскресенье недели>/
и идут фоном в ролики.

Состояние не хранится: Telegram сам помнит, какие сообщения уже обработаны (offset),
а кнопка «Опубликовать» копирует в канал уже присланное превью.
"""
import datetime as dt, json, os, re, subprocess, sys, tempfile, time, glob
from zoneinfo import ZoneInfo
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
MSK = ZoneInfo("Europe/Moscow")
TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN = os.environ.get("ADMIN_CHAT_ID", "")
CHANNEL = os.environ.get("CHANNEL", "@gladkie_linii_msk")
# Реакции бота на посты канала, по очереди (карусель); пусто — не ставить.
REACTIONS = [e.strip() for e in os.environ.get("REACTIONS", "🔥,❤,👍").split(",") if e.strip()]
API = f"https://api.telegram.org/bot{TOKEN}/"

DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
# Фразы из прошлых постов канала; берутся по очереди по дате.
SLOGANS = [
    "Твоя кожа достойна шелка. Доверься световому прикосновению",
    "Ухоженная женщина - это не про деньги, а про любовь к себе",
    "Забудьте о воске и сахаре. Осень ~ это время высоких технологий и комфорта 👍",
    "Природа готовится ко сну, а мы готовим вашу кожу",
]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
HELP = ("Пришлите дату и время свободных окон, например:\n"
        "30.09 11:00, 13:30 или 14:00, 18:00\n"
        "завтра 12:00 15:00\n"
        "Можно несколько строк, по ролику на каждую дату.\n"
        "Своя фраза для ролика — первой строкой, без даты, например:\n"
        "Осень — время гладкой кожи\n30.09 11:00, 15:00\n"
        "Фоны: присылайте вертикальные видео (5–15 с) или фото файлом — так качество лучше. "
        "Я пришлю превью, а в канал оно уйдёт только после кнопки «Опубликовать».")


def api(method, files=None, **params):
    r = requests.post(API + method, data=params, files=files, timeout=120)
    js = r.json()
    if not js.get("ok"):
        raise RuntimeError(f"{method}: {js.get('description')}")
    return js["result"]


DATE_START = re.compile(r"^(\d{1,2}[./]\d{1,2}|сегодня|завтра|послезавтра)")


def react(message_id):
    """Поставить на пост канала реакцию; какая из карусели — зависит от номера поста,
    поэтому повторный вызов ставит ту же самую."""
    if not REACTIONS:
        return None
    emoji = REACTIONS[int(message_id) % len(REACTIONS)]
    api("setMessageReaction", chat_id=CHANNEL, message_id=message_id,
        reaction=json.dumps([{"type": "emoji", "emoji": emoji}]))
    return emoji


def parse_line(line, today):
    """'30.09 11:00, 14:30' -> (date, ['11:00', '14:30']); ошибки -> ValueError с понятным текстом."""
    s = line.strip().lower()
    if not s:
        return None
    if s.startswith("сегодня"):
        date, rest = today, s[len("сегодня"):]
    elif s.startswith("послезавтра"):
        date, rest = today + dt.timedelta(days=2), s[len("послезавтра"):]
    elif s.startswith("завтра"):
        date, rest = today + dt.timedelta(days=1), s[len("завтра"):]
    else:
        m = re.match(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", s)
        if not m:
            raise ValueError(f"не нашёл дату в «{line.strip()}» (нужно, например, 30.09)")
        d, mo, y = int(m[1]), int(m[2]), m[3]
        year = (int(y) + 2000 if len(y) == 2 else int(y)) if y else today.year
        try:
            date = dt.date(year, mo, d)
        except ValueError:
            raise ValueError(f"такой даты нет: «{m[0]}»")
        if not y and date < today - dt.timedelta(days=7):
            date = date.replace(year=year + 1)
        rest = s[m.end():]
    times = []  # каждое окно: "14:00" или "13:30 или 14:00"
    join = False
    for tok in re.findall(r"\d{1,2}(?:[:.\-]\d{2})?|или|/", rest):
        if tok in ("или", "/"):
            join = bool(times)
            continue
        h, _, mi = re.sub(r"[.\-]", ":", tok).partition(":")
        h, mi = int(h), int(mi or 0)
        if h > 23 or mi > 59:
            raise ValueError(f"странное время: {tok}")
        t = f"{h:02d}:{mi:02d}"
        if join:
            times[-1] += f" или {t}"
        elif t not in times:
            times.append(t)
        join = False
    if not times:
        raise ValueError(f"не нашёл время в «{line.strip()}» (нужно, например, 14:30)")
    if len(times) > 10:
        raise ValueError("в одном ролике помещается до 10 окон, разбейте на две строки")
    times.sort(key=lambda s: s[:5])
    return date, times


def caption(date, times, phrase=None):
    """Подпись как в постах канала (parse_mode=HTML)."""
    import html
    slogan = html.escape(phrase) if phrase else SLOGANS[date.toordinal() % len(SLOGANS)]
    return (f"🍃 Свободное время 🍃\n"
            f"📆 <b>{date.day} {MONTHS[date.month - 1]} - {DAYS[date.weekday()]}</b>\n"
            f"🕐 {', '.join(times)}\n\n"
            f"🌸 <i>{slogan}</i> 🌸\n\n"
            f"«Гладкие линии» - красота каждый день !\n\n"
            f'<a href="https://t.me/+79055372707">ЗАПИСЬ / КОНСУЛЬТАЦИЯ ПО ССЫЛКЕ</a> 🔗\n\n'
            f"———-\n"
            f"Ⓜ️ Улица Дмитриевского\n"
            f"📍 Москва, ул. Дмитриевского, 3\n"
            f"🅿️ Бесплатная парковка\n⠀\n"
            f"📲 +7 (905) 537-27-07\n⠀\n"
            f"———-\n"
            f"#лазернаяэпиляция #лазер #москва #кожухово #дмитриевского")


def render(date, times, out, phrase=None):
    extra = ["--slogan", phrase] if phrase else []
    r = subprocess.run([sys.executable, os.path.join(HERE, "make_video.py"), "--date", date.isoformat(),
                        "--slots", *times, *extra, "-o", out], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("не получилось собрать ролик: " + (r.stderr.strip().splitlines() or ["?"])[-1])


def send_preview(chat, date, times, phrase=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"okna_{date.isoformat()}.mp4")
        render(date, times, path, phrase)
        with open(path, "rb") as f:
            msg = api("sendVideo", files={"video": f}, chat_id=chat, caption=caption(date, times, phrase), parse_mode="HTML",
                      width=1080, height=1920, supports_streaming="true")
    kb = '{"inline_keyboard":[[{"text":"Опубликовать","callback_data":"pub:%d"},' \
         '{"text":"Отменить","callback_data":"del:%d"}]]}' % (msg["message_id"], msg["message_id"])
    api("editMessageReplyMarkup", chat_id=chat, message_id=msg["message_id"], reply_markup=kb)


TEMPLATES = os.path.join(HERE, "assets", "templates")
ASK_TEXT = ("Воскресенье: пришлите, пожалуйста, новые фоны для роликов на эту неделю. "
            "Лучше всего короткие вертикальные видео (5–15 секунд) или фото, отправленные файлом, "
            "без надписей. Если не пришлёте, останутся фоны прошлой недели.")


def week_folder(today):
    """Набор недели называется датой её воскресенья."""
    sunday = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    return os.path.join(TEMPLATES, sunday.isoformat())


def git_save(path, message):
    """В GitHub Actions сохраняет картинку в репозиторий, чтобы следующие запуски её видели."""
    if os.environ.get("GIT_PUSH") != "1":
        return
    run = lambda *a: subprocess.run(["git", "-C", HERE, *a], check=True, capture_output=True)
    run("add", "-f", path)
    run("-c", "user.name=gladkie-bot", "-c", "user.email=bot@users.noreply.github.com", "commit", "-m", message)
    for _ in range(3):
        try:
            run("pull", "--rebase", "origin", "main"); run("push", "origin", "HEAD:main"); return
        except subprocess.CalledProcessError:
            time.sleep(3)
    raise RuntimeError("не удалось сохранить картинку в репозиторий")


def media_of(m):
    """Что прислали: ("image"|"video", file) или None."""
    doc = m.get("document") or {}
    mime = doc.get("mime_type", "")
    if m.get("photo"):
        return "image", m["photo"][-1]
    if mime.startswith("image/") or doc.get("file_name", "").lower().endswith((".heic", ".heif")):
        return "image", doc
    if m.get("video"):
        return "video", m["video"]
    if m.get("animation"):
        return "video", m["animation"]
    if mime.startswith("video/"):
        return "video", doc
    return None


def save_template(chat, m, kind, f):
    if f.get("file_size", 0) > 20 * 1024 * 1024:
        api("sendMessage", chat_id=chat, text="Файл больше 20 МБ, Telegram не даёт боту его скачать. "
                                              "Пришлите покороче или сожмите, пожалуйста.")
        return
    info = api("getFile", file_id=f["file_id"])
    data = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{info['file_path']}", timeout=300).content
    folder = week_folder(dt.datetime.now(MSK).date())
    os.makedirs(folder, exist_ok=True)
    uid = f["file_unique_id"]
    if kind == "image":
        from PIL import Image, ImageOps
        import io
        try:
            import pillow_heif; pillow_heif.register_heif_opener()  # фото с iPhone
        except ImportError:
            pass
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        im.thumbnail((2160, 3840))  # полное качество, но не больше 4K
        path = os.path.join(folder, f"{uid}.jpg")
        im.save(path, quality=94)
        what = "Картинку"
    else:
        import imageio_ffmpeg
        with tempfile.NamedTemporaryFile(suffix=".bin") as src:
            src.write(data); src.flush()
            path = os.path.join(folder, f"{uid}.mp4")
            r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", src.name,
                                "-t", "15", "-an", "-vf",
                                "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
                                "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p", path],
                               capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("не получилось обработать видео")
        what = "Видео"
    git_save(path, f"Фон для роликов {os.path.basename(folder)}")
    n = len([p for p in glob.glob(os.path.join(folder, "*")) if p.endswith((".jpg", ".mp4"))])
    api("sendMessage", chat_id=chat, text=f"{what} сохранил, фонов в наборе этой недели: {n}. Ролики будут с ними.")


def ask_templates():
    api("sendMessage", chat_id=ADMIN, text=ASK_TEXT)


def on_message(m):
    chat = str(m["chat"]["id"])
    text = m.get("text", "")
    if chat != ADMIN:
        if m["chat"]["type"] == "private":
            api("sendMessage", chat_id=chat,
                text=f"Этот бот работает только для владельца канала. Ваш id: {chat}")
        return
    media = media_of(m)
    if media:
        save_template(chat, m, *media)
        return
    if not text or text.startswith("/"):
        api("sendMessage", chat_id=chat, text=HELP)
        return
    today = dt.datetime.now(MSK).date()
    lines = [l for l in text.splitlines() if l.strip()]
    phrase = None
    if len(lines) > 1 and not DATE_START.match(lines[0].strip().lower()):
        phrase = lines.pop(0).strip()  # первая строка без даты — фраза дня
    try:
        items = [p for p in (parse_line(l, today) for l in lines) if p]
    except ValueError as e:
        api("sendMessage", chat_id=chat, text=f"Не понял: {e}.\n\n{HELP}")
        return
    if not items:
        api("sendMessage", chat_id=chat, text=HELP)
        return
    api("sendMessage", chat_id=chat, text="Делаю ролик, это около минуты…")
    for date, times in items:
        send_preview(chat, date, times, phrase)


def on_callback(q):
    chat = str(q["message"]["chat"]["id"])
    if chat != ADMIN:
        return api("answerCallbackQuery", callback_query_id=q["id"])
    action, mid = q["data"].split(":")
    if action == "pub":
        post = api("copyMessage", chat_id=CHANNEL, from_chat_id=chat, message_id=mid)
        try:  # если в канале выключены реакции, пост всё равно публикуется
            react(post["message_id"])
        except Exception as e:
            print("Реакция не поставлена:", e)
        api("editMessageReplyMarkup", chat_id=chat, message_id=mid,
            reply_markup='{"inline_keyboard":[[{"text":"✅ Опубликовано","callback_data":"noop:0"}]]}')
        api("answerCallbackQuery", callback_query_id=q["id"], text="Опубликовано в канале")
    elif action == "del":
        api("deleteMessage", chat_id=chat, message_id=mid)
        api("answerCallbackQuery", callback_query_id=q["id"], text="Отменено")
    else:
        api("answerCallbackQuery", callback_query_id=q["id"])


def poll(timeout):
    updates = api("getUpdates", timeout=timeout, allowed_updates='["message","callback_query"]')
    for u in updates:
        api("getUpdates", offset=u["update_id"] + 1, timeout=0)  # подтверждаем до обработки: без повторов
        try:
            if "message" in u:
                on_message(u["message"])
            elif "callback_query" in u:
                on_callback(u["callback_query"])
        except Exception as e:
            print("error:", e, file=sys.stderr)
            if ADMIN:
                try:
                    api("sendMessage", chat_id=ADMIN, text=f"Ошибка: {e}")
                except Exception:
                    pass
    return len(updates)


def main():
    if not TOKEN:
        sys.exit("BOT_TOKEN не задан")
    if "--ask-templates" in sys.argv:
        ask_templates()
    elif "--loop" in sys.argv:  # --loop [секунд]: слушать постоянно или заданное время
        i = sys.argv.index("--loop")
        stop = time.time() + float(sys.argv[i + 1]) if len(sys.argv) > i + 1 else float("inf")
        while time.time() < stop:
            try:
                poll(int(max(1, min(50, stop - time.time()))))
            except Exception as e:
                print("error:", e, file=sys.stderr)
                time.sleep(5)
    else:
        poll(0)


if __name__ == "__main__":
    main()
