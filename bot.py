#!/usr/bin/env python3
"""Telegram-бот: дата и время свободных окон -> ролик -> превью -> публикация в канал.

Переменные окружения:
  BOT_TOKEN      токен от @BotFather (секрет)
  ADMIN_CHAT_ID  id чата Ивана; только ему бот отвечает и присылает превью
  CHANNEL        канал для публикации, по умолчанию @gladkie_linii_msk

Режимы:
  python3 bot.py          один проход по новым сообщениям (для GitHub Actions по расписанию)
  python3 bot.py --loop   работать постоянно (для своего сервера)

Состояние не хранится: Telegram сам помнит, какие сообщения уже обработаны (offset),
а кнопка «Опубликовать» копирует в канал уже присланное превью.
"""
import datetime as dt, os, re, subprocess, sys, tempfile, time
from zoneinfo import ZoneInfo
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
MSK = ZoneInfo("Europe/Moscow")
TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN = os.environ.get("ADMIN_CHAT_ID", "")
CHANNEL = os.environ.get("CHANNEL", "@gladkie_linii_msk")
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
        "Можно несколько строк, по ролику на каждую дату. "
        "Я пришлю превью, а в канал оно уйдёт только после кнопки «Опубликовать».")


def api(method, files=None, **params):
    r = requests.post(API + method, data=params, files=files, timeout=120)
    js = r.json()
    if not js.get("ok"):
        raise RuntimeError(f"{method}: {js.get('description')}")
    return js["result"]


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


def caption(date, times):
    """Подпись как в постах канала (parse_mode=HTML)."""
    slogan = SLOGANS[date.toordinal() % len(SLOGANS)]
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


def render(date, times, out):
    subprocess.run([sys.executable, os.path.join(HERE, "make_video.py"), "--date", date.isoformat(),
                    "--slots", *times, "-o", out], check=True, capture_output=True)


def send_preview(chat, date, times):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"okna_{date.isoformat()}.mp4")
        render(date, times, path)
        with open(path, "rb") as f:
            msg = api("sendVideo", files={"video": f}, chat_id=chat, caption=caption(date, times), parse_mode="HTML",
                      width=720, height=1280, supports_streaming="true")
    kb = '{"inline_keyboard":[[{"text":"Опубликовать","callback_data":"pub:%d"},' \
         '{"text":"Отменить","callback_data":"del:%d"}]]}' % (msg["message_id"], msg["message_id"])
    api("editMessageReplyMarkup", chat_id=chat, message_id=msg["message_id"], reply_markup=kb)


def on_message(m):
    chat = str(m["chat"]["id"])
    text = m.get("text", "")
    if chat != ADMIN:
        if m["chat"]["type"] == "private":
            api("sendMessage", chat_id=chat,
                text=f"Этот бот работает только для владельца канала. Ваш id: {chat}")
        return
    if not text or text.startswith("/"):
        api("sendMessage", chat_id=chat, text=HELP)
        return
    today = dt.datetime.now(MSK).date()
    try:
        items = [p for p in (parse_line(l, today) for l in text.splitlines()) if p]
    except ValueError as e:
        api("sendMessage", chat_id=chat, text=f"Не понял: {e}.\n\n{HELP}")
        return
    if not items:
        api("sendMessage", chat_id=chat, text=HELP)
        return
    api("sendMessage", chat_id=chat, text="Делаю ролик, это около минуты…")
    for date, times in items:
        send_preview(chat, date, times)


def on_callback(q):
    chat = str(q["message"]["chat"]["id"])
    if chat != ADMIN:
        return api("answerCallbackQuery", callback_query_id=q["id"])
    action, mid = q["data"].split(":")
    if action == "pub":
        api("copyMessage", chat_id=CHANNEL, from_chat_id=chat, message_id=mid)
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
    if "--loop" in sys.argv:
        while True:
            try:
                poll(50)
            except Exception as e:
                print("error:", e, file=sys.stderr)
                time.sleep(5)
    else:
        poll(0)


if __name__ == "__main__":
    main()
