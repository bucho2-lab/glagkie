#!/usr/bin/env python3
"""Ролик «Свободное время» для канала «Гладкие линии».

Стиль первого варианта: пудрово-розовая дымка, плавные белые линии, надписи и плашки
с временем появляются по очереди. Фоном идёт картинка из последнего набора assets/templates
(бот собирает их по воскресеньям), без картинок остаётся розовый градиент.
Музыку сочиняет music.py, лицензия не нужна.

Пример:
  python3 make_video.py --date 2026-09-30 --slots 11:00 "13:30 или 14:00" 18:00 -o out.mp4
"""
import argparse, datetime as dt, glob, math, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageOps
import imageio_ffmpeg
import music

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, DUR = 1080, 1920, 30, 12.0
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONT = os.path.join(HERE, "fonts", "Prata-Regular.ttf")
LOGO = os.path.join(HERE, "assets", "logo.png")
TEMPLATES = os.path.join(HERE, "assets", "templates")
BG_TOP, BG_BOT = (250, 232, 226), (231, 196, 190)
INK, ACCENT = (74, 44, 52), (176, 92, 104)
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
PHONE = "Запись: +7 (905) 537-27-07"
ADDRESS = "ул. Дмитриевского, 3 · бесплатная парковка"


def font(size): return ImageFont.truetype(FONT, size)
def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3


def latest_templates():
    """Картинки из самой свежей папки assets/templates/ГГГГ-ММ-ДД."""
    sets = sorted(d for d in glob.glob(os.path.join(TEMPLATES, "*")) if os.path.isdir(d))
    for d in reversed(sets):
        pics = sorted(glob.glob(os.path.join(d, "*.jpg")) + glob.glob(os.path.join(d, "*.png")))
        if pics:
            return pics
    return []


def gradient():
    g = Image.new("RGB", (1, 256))
    for y in range(256):
        g.putpixel((0, y), tuple(int(a + (b - a) * y / 255) for a, b in zip(BG_TOP, BG_BOT)))
    return g.resize((W, H), Image.BILINEAR)


def background(picture):
    """Картинка под розовой дымкой: сверху и снизу плотнее, в середине её лучше видно."""
    grad = gradient().convert("RGBA")
    if not picture:
        return grad, None
    pic = ImageOps.fit(Image.open(picture).convert("RGB"), (int(W * 1.08), int(H * 1.08)), Image.LANCZOS)
    mask = Image.new("L", (1, 256))
    for y in range(256):
        k = y / 255
        mask.putpixel((0, y), int(255 * (0.62 + 0.25 * (abs(k - 0.45) * 2) ** 1.5)))
    grad.putalpha(mask.resize((W, H), Image.BILINEAR))
    return grad, pic


def bg_frame(veil, pic, t):
    if pic is None:
        return veil.copy()
    z = 1.0 + 0.07 * t / DUR  # медленное приближение
    w, h = pic.width / z, pic.height / z
    x, y = (pic.width - w) / 2, (pic.height - h) / 2 + 20 * math.sin(t / DUR * math.pi)
    fr = pic.resize((W, H), Image.BILINEAR, box=(x, y, x + w, y + h)).convert("RGBA")
    fr.alpha_composite(veil)
    return fr


def waves(fr, t):
    d = ImageDraw.Draw(fr, "RGBA")
    for i in range(4):
        base = 1500 + i * 70
        pts = [(x, base + 60 * math.sin(x / 260 + t * 0.9 + i * 0.8) + 25 * math.sin(x / 90 - t * 0.6 + i))
               for x in range(-20, W + 40, 20)]
        d.line(pts, fill=(255, 255, 255, 120 - i * 22), width=5)
    for i in range(3):
        pts = [(x, 140 + i * 55 + 45 * math.sin(x / 300 - t * 0.7 + i * 1.3)) for x in range(-20, W + 40, 20)]
        d.line(pts, fill=(255, 255, 255, 100 - i * 28), width=4)


def text_sprite(text, f, color):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    im = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=f, fill=color + (255,))
    return im


def fit_font(text, size, width):
    f = font(size)
    while ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=f) > width and size > 24:
        size -= 2; f = font(size)
    return f


def pill_sprite(w, h, text, f):
    im = Image.new("RGBA", (int(w) + 8, int(h) + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((4, 4, 4 + w, 4 + h), radius=h / 2, fill=(255, 255, 255, 235),
                                        outline=ACCENT + (255,), width=4)
    ts = text_sprite(text, f, ACCENT)
    im.alpha_composite(ts, (int(4 + w / 2 - ts.width / 2), int(4 + h / 2 - ts.height / 2)))
    return im


class El:
    """Появляется в момент start: проявляется и всплывает; плашки потом слегка «дышат»."""
    def __init__(self, img, cx, cy, start, pulse=False):
        self.img, self.cx, self.cy, self.start, self.pulse = img, cx, cy, start, pulse

    def draw(self, fr, t):
        a = ease((t - self.start) / 0.6)
        if a <= 0:
            return
        img = self.img
        if self.pulse and a >= 1:
            s = 1 + 0.02 * math.sin((t - self.start) * 3)
            img = img.resize((int(img.width * s), int(img.height * s)), Image.BILINEAR)
        elif a < 1:
            img = img.copy(); img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
        fr.alpha_composite(img, (int(self.cx - img.width / 2), int(self.cy - img.height / 2 + (1 - a) * 45)))


def build(date, slots):
    els = []
    lg = Image.open(LOGO).convert("RGBA").resize((200, 200), Image.LANCZOS)
    els.append(El(lg, W / 2, 330, 0.1))
    els.append(El(text_sprite("СВОБОДНОЕ ВРЕМЯ", font(80), ACCENT), W / 2, 530, 0.3))
    els.append(El(text_sprite("«Гладкие линии» · лазерная эпиляция", font(44), INK), W / 2, 615, 0.6))
    els.append(El(text_sprite(f"{date.day} {MONTHS[date.month - 1]}", font(118), INK), W / 2, 760, 1.1))
    els.append(El(text_sprite(DAYS[date.weekday()], font(58), INK), W / 2, 880, 1.3))

    n = len(slots)
    if n <= 4:
        ph, gap, f = 124, 30, font(78)
        rows = [[s] for s in slots]
    else:
        ph, gap, f = (104, 24, font(58)) if n <= 8 else (92, 18, font(50))
        rows, pair = [], []
        for sl in slots:  # «13:30 или 14:00» и непарная плашка — отдельной строкой
            if "или" in sl:
                if pair: rows.append(pair); pair = []
                rows.append([sl])
            else:
                pair.append(sl)
                if len(pair) == 2: rows.append(pair); pair = []
        if pair: rows.append(pair)
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    top, j = 990, 0
    for r, row in enumerate(rows):
        cy = top + r * (ph + gap) + ph / 2
        for c, sl in enumerate(row):
            if len(row) == 1:
                pw, cx = max(420, d.textlength(sl, font=f) + 120), W / 2
            else:
                pw, cx = 420, W / 2 + (c - 0.5) * 450
            els.append(El(pill_sprite(pw, ph, sl, f), cx, cy, 1.9 + 0.3 * j, pulse=True)); j += 1

    t0 = 1.9 + 0.3 * j + 0.3
    els.append(El(text_sprite(PHONE, fit_font(PHONE, 54, W - 120), INK), W / 2, 1720, t0))
    els.append(El(text_sprite(ADDRESS, fit_font(ADDRESS, 38, W - 120), INK), W / 2, 1795, t0 + 0.2))
    return els


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="ГГГГ-ММ-ДД")
    p.add_argument("--slots", nargs="+", required=True, help='время, например 11:00 "13:30 или 14:00"')
    p.add_argument("--picture", help="картинка для фона (по умолчанию из последнего набора)")
    p.add_argument("-o", "--out", default="slot.mp4")
    a = p.parse_args()
    date = dt.date.fromisoformat(a.date)
    pics = latest_templates()
    picture = a.picture or (pics[date.toordinal() % len(pics)] if pics else None)
    veil, pic = background(picture)
    els = build(date, a.slots[:10])

    with tempfile.TemporaryDirectory() as tmp:
        track = music.compose(DUR, date.toordinal(), os.path.join(tmp, "music.wav"))
        cmd = [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-i", track, "-map", "0:v", "-map", "1:a",
               "-af", f"afade=t=in:d=0.5,afade=t=out:st={DUR - 1.5}:d=1.5", "-c:a", "aac", "-b:a", "128k",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
               "-movflags", "+faststart", "-shortest", a.out]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        base = Image.new("RGBA", (W, H), BG_TOP + (255,))
        for i in range(int(DUR * FPS)):
            t = i / FPS
            fr = bg_frame(veil, pic, t)
            waves(fr, t)
            for e in els:
                e.draw(fr, t)
            fade = min(1.0, t / 0.4, (DUR - t) / 0.5)
            if fade < 1:
                fr = Image.blend(base, fr, max(0.0, fade))
            proc.stdin.write(fr.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait():
            raise SystemExit("ffmpeg error")
    print(a.out)


if __name__ == "__main__":
    main()
