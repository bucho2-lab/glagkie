#!/usr/bin/env python3
"""Ролик «Свободное время» для канала «Гладкие линии».

Фон — всегда чёткая картинка из самого свежего набора assets/templates (бот собирает их по воскресеньям;
0000-default — запасной набор). Два стиля анимации чередуются по дням:
  lines  — первый вариант: плавные белые линии, белые плашки, надписи всплывают по очереди;
  glass  — как в роликах канала: стеклянные плашки выезжают по бокам, блики, блёстки, логотип «дышит».
Цвет текста подбирается под яркость фона за ним, чтобы надписи читались.
Музыка из assets/music (ролики канала), если папка пуста — music.py.

Пример:
  python3 make_video.py --date 2026-09-30 --slots 11:00 "13:30 или 14:00" 18:00 -o out.mp4
"""
import argparse, datetime as dt, glob, math, os, random, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageChops, ImageStat
import imageio_ffmpeg
import music

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, DUR = 1080, 1920, 30, 12.0
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONT = os.path.join(HERE, "fonts", "Prata-Regular.ttf")
LOGO = os.path.join(HERE, "assets", "logo.png")
TEMPLATES = os.path.join(HERE, "assets", "templates")
MUSIC = sorted(glob.glob(os.path.join(HERE, "assets", "music", "*.m4a")))
INK, ACCENT, WHITE = (60, 36, 44), (176, 92, 104), (255, 255, 255)
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
SLOGANS = [  # фразы из прошлых роликов канала
    "«ГЛАДКИЕ ЛИНИИ» - СВОБОДА - ЭТО ПРОСНУТЬСЯ И НЕ ДУМАТЬ О БРИТВЕ.",
    "«ГЛАДКИЕ ЛИНИИ» - УХОД ЗА СОБОЙ - ЭТО НЕ ТРАТА ВРЕМЕНИ. ЭТО ИНВЕСТИЦИЯ В СВОЕ «ЗАВТРА»",
    "«ГЛАДКИЕ ЛИНИИ» - УХОЖЕННАЯ ЖЕНЩИНА - СЧАСТЛИВАЯ ЖЕНЩИНА",
    "«ГЛАДКИЕ ЛИНИИ» - ВАША КОЖА БЕЗУПРЕЧНА КАЖДЫЙ ДЕНЬ!",
    "«ГЛАДКИЕ ЛИНИИ» - ЖЕНСКАЯ ЭНЕРГИЯ ЛЮБИТ БЕРЕЖНЫЙ УХОД. ЗАПИШИТЕСЬ НА ПРОЦЕДУРУ - НАПОЛНИТЕСЬ СИЯНИЕМ",
    "КОГДА ЖЕНЩИНА НАЧИНАЕТ ЗАБОТИТЬСЯ О СЕБЕ ОНА НЕ СТАНОВИТСЯ ЭГОИСТКОЙ. ОНА СТАНОВИТСЯ СЧАСТЛИВОЙ",
]
BEATS = []  # доли такта текущего трека
LOGO_C, LOGO_R = (288, 1604), 230  # логотип слева внизу, как в роликах канала
RIGHT_X = 800                        # колонка справа от логотипа


def font(size): return ImageFont.truetype(FONT, size)
def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def ease_back(x): x = max(0.0, min(1.0, x)); c = 1.4; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2
def textlen(text, f): return ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=f)


# ---------- фон ----------

def pictures():
    """Картинки самого свежего набора; 0000-default — запасной."""
    for d in sorted((d for d in glob.glob(os.path.join(TEMPLATES, "*")) if os.path.isdir(d)), reverse=True):
        pics = sorted(sum((glob.glob(os.path.join(d, e)) for e in ("*.jpg", "*.png", "*.mp4")), []))
        if pics:
            return pics
    raise SystemExit("нет картинок в assets/templates")


def load_picture(path):
    """Кадрирование под 9:16 с запасом на приближение, без размытия; мелкие фото слегка подтачиваются."""
    im = Image.open(path).convert("RGB")
    im = ImageOps.exif_transpose(im)
    pw, ph = int(W * 1.06), int(H * 1.06)
    small = im.width < pw * 0.8
    im = ImageOps.fit(im, (pw, ph), Image.LANCZOS, centering=(0.5, 0.4))
    if small:
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    return im


def bg_frame(pic, t):
    z = 1.0 + 0.05 * t / DUR  # медленное приближение
    w, h = W / z, H / z
    x, y = (pic.width - w) / 2, (pic.height - h) / 2
    return pic.resize((W, H), Image.BICUBIC, box=(x, y, x + w, y + h)).convert("RGBA")


class VideoBg:
    """Видео-фон: кадрируется под 9:16 и крутится по кругу, если короче ролика."""
    def __init__(self, path):
        self.path = path
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=rgb24"
        self.proc = subprocess.Popen([FF, "-loglevel", "error", "-stream_loop", "-1", "-i", path, "-t", str(DUR),
                                      "-vf", vf, "-an", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        self.last = None

    def frame(self, t):
        raw = self.proc.stdout.read(W * H * 3)
        if len(raw) == W * H * 3:
            self.last = Image.frombytes("RGB", (W, H), raw)
        return self.last.convert("RGBA")

    def still(self, t):
        raw = subprocess.run([FF, "-loglevel", "error", "-ss", str(t), "-i", self.path, "-frames:v", "1",
                              "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if len(raw) < W * H * 3:  # короткое видео: берём первый кадр
            raw = subprocess.run([FF, "-loglevel", "error", "-i", self.path, "-frames:v", "1", "-vf",
                                  f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        return Image.frombytes("RGB", (W, H), raw[: W * H * 3]).convert("RGBA")


class PictureBg:
    def __init__(self, path):
        self.pic = load_picture(path)

    def frame(self, t): return bg_frame(self.pic, t)
    def still(self, t): return bg_frame(self.pic, t)


def beats(track):
    """Доли такта в треке: сила атак звука + темп по автокорреляции."""
    import numpy as np
    sr, hop = 22050, 512
    raw = subprocess.run([FF, "-loglevel", "error", "-stream_loop", "-1", "-i", track, "-t", str(DUR), "-ac", "1",
                          "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    if len(x) < sr * 2:
        return [i * 0.5 for i in range(int(DUR * 2))]
    n = (len(x) - 2048) // hop
    frames = np.stack([x[i * hop:i * hop + 2048] * np.hanning(2048) for i in range(n)])
    spec = np.log1p(np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(spec, axis=0)).sum(axis=1)
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    fps = sr / hop
    lags = np.arange(int(fps * 60 / 170), int(fps * 60 / 70))
    ac = [np.dot(flux[:-l], flux[l:]) for l in lags]
    period = lags[int(np.argmax(ac))]
    phase = max(range(period), key=lambda p: flux[p::period].sum())
    return [(phase + i * period) / fps for i in range(int((len(flux) - phase) / period) + 1)]


def snap(t, grid):
    return min(grid, key=lambda g: abs(g - t)) if grid else t


class Palette:
    """Цвет надписи под яркость фона в её месте: на светлом — тёмный, на тёмном — белый."""
    def __init__(self, base):
        self.gray = base.convert("L")

    def light(self, box):
        x0, y0, x1, y1 = (int(max(0, v)) for v in box)
        return ImageStat.Stat(self.gray.crop((x0, y0, min(W, x1), min(H, y1)))).mean[0] > 140

    def text(self, box, dark=INK):
        return (dark, (255, 255, 255, 230)) if self.light(box) else (WHITE, (0, 0, 0, 210))


# ---------- спрайты ----------

def text_sprite(text, f, color, halo, pad=16):
    """Надпись с мягким ореолом контрастного цвета — читается на любом фоне."""
    l, t, r, b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)
    im = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pad - l, pad - t), text, font=f, fill=halo, stroke_width=3, stroke_fill=halo)
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(1)))
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=f, fill=color + (255,))
    return im


def clock(d, cx, cy, r, c):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=3)
    d.line([cx, cy, cx, cy - r * 0.6], fill=c, width=3)
    d.line([cx, cy, cx + r * 0.45, cy + r * 0.25], fill=c, width=3)


def pill_sprite(w, h, text, f, style, light_bg):
    pad = 10
    im = Image.new("RGBA", (int(w) + 2 * pad, int(h) + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = (pad, pad, pad + w, pad + h)
    if style == "lines":
        d.rounded_rectangle(box, radius=h / 2, fill=(255, 255, 255, 238), outline=ACCENT + (255,), width=4)
        color, halo = ACCENT, (255, 255, 255, 0)
    else:  # стекло: на светлом фоне — затемнённое, на тёмном — светлое
        fill = (40, 25, 30, 95) if light_bg else (255, 255, 255, 45)
        d.rounded_rectangle(box, radius=h / 2, fill=fill, outline=(255, 255, 255, 170), width=3)
        clock(d, pad + h * 0.55, pad + h / 2, h * 0.2, (255, 255, 255, 150))
        color, halo = WHITE, (0, 0, 0, 150)
    ts = text_sprite(text, f, color, halo)
    shift = 0 if style == "lines" else h * 0.15
    im.alpha_composite(ts, (int(pad + w / 2 + shift - ts.width / 2), int(pad + h / 2 - ts.height / 2)))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=h / 2, fill=255)
    return im, mask


class El:
    """Элемент: появляется в start. rise — всплывает; left/right/up — выезжает с «перелётом»."""
    def __init__(self, img, cx, cy, start, kind="rise", mask=None, pulse=False):
        self.img, self.cx, self.cy, self.start, self.kind, self.mask, self.pulse = img, cx, cy, start, kind, mask, pulse

    def draw(self, fr, t):
        k = (t - self.start) / 0.6
        if k <= 0:
            return
        a, img, dx, dy = ease(k), self.img, 0, 0
        if self.kind == "rise":
            dy = (1 - a) * 45
        else:
            s = 0.85 + 0.15 * ease_back(k)
            if s != 1:
                img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BILINEAR)
            off = (1 - a) * 130
            dx = {"left": -off, "right": off}.get(self.kind, 0)
            dy = off * 0.5 if self.kind == "up" else 0
        if self.pulse and a >= 1 and BEATS:
            since = min((t - b for b in BEATS if b <= t), default=9)
            s = 1 + 0.035 * math.exp(-since * 9)  # «толчок» на каждую долю
            if s > 1.002:
                img = img.resize((int(img.width * s), int(img.height * s)), Image.BILINEAR)
        if a < 1:
            img = img.copy(); img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
        fr.alpha_composite(img, (int(self.cx - img.width / 2 + dx), int(self.cy - img.height / 2 + dy)))

    def glint(self, fr, t, at):
        k = (t - at) / 0.7
        if not 0 < k < 1 or self.mask is None:
            return
        w, h = self.img.size
        band = Image.new("L", (w, h), 0)
        x = -90 + k * (w + 180)
        ImageDraw.Draw(band).polygon([(x, 0), (x + 60, 0), (x + 60 - h * 0.6, h), (x - h * 0.6, h)], fill=110)
        band = ImageChops.multiply(band.filter(ImageFilter.GaussianBlur(12)), self.mask)
        light = Image.new("RGBA", (w, h), (255, 255, 255, 0)); light.putalpha(band)
        fr.alpha_composite(light, (int(self.cx - w / 2), int(self.cy - h / 2)))


# ---------- анимации поверх ----------

def waves(fr, t):
    d = ImageDraw.Draw(fr, "RGBA")
    for i in range(3):
        pts = [(x, 110 + i * 55 + 45 * math.sin(x / 300 - t * 0.7 + i * 1.3)) for x in range(-20, W + 40, 20)]
        d.line(pts, fill=(255, 255, 255, 150 - i * 35), width=4)


def star(r):
    s = r * 4; c = s / 2
    im = Image.new("L", (s, s), 0)
    ImageDraw.Draw(im).polygon([(c, c - 2 * r), (c + r * .18, c - r * .18), (c + 2 * r, c), (c + r * .18, c + r * .18),
                                (c, c + 2 * r), (c - r * .18, c + r * .18), (c - 2 * r, c), (c - r * .18, c - r * .18)], fill=255)
    glow = Image.new("L", (s, s), 0); ImageDraw.Draw(glow).ellipse((c - r, c - r, c + r, c + r), fill=160)
    im = ImageChops.lighter(im, glow.filter(ImageFilter.GaussianBlur(r * 0.6)))
    out = Image.new("RGBA", (s, s), (255, 250, 235, 0)); out.putalpha(im)
    return out


class Sparkles:
    def __init__(self, seed, n=40):
        rnd = random.Random(seed)
        self.sprites = [star(r) for r in (4, 7, 10)]
        self.p = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.randrange(3), rnd.uniform(0, 6.28),
                   rnd.uniform(1.5, 3.5), rnd.uniform(12, 35)) for _ in range(n)]

    def draw(self, fr, t):
        for x, y, si, ph, sp, drift in self.p:
            a = max(0.0, math.sin(t * sp + ph)) ** 2 * min(1.0, t / 1.5)
            if a < 0.05:
                continue
            spr = self.sprites[si].copy(); spr.putalpha(spr.getchannel("A").point(lambda v: int(v * a)))
            fr.alpha_composite(spr, (int(x - spr.width / 2), int((y - t * drift) % H - spr.height / 2)))


class Logo:
    def __init__(self, glint):
        self.img = Image.open(LOGO).convert("RGBA").resize((LOGO_R * 2, LOGO_R * 2), Image.LANCZOS)
        self.mask = Image.new("L", self.img.size, 0)
        ImageDraw.Draw(self.mask).ellipse((0, 0, self.img.width - 1, self.img.height - 1), fill=255)
        self.glint = glint

    def draw(self, fr, t):
        a = ease(t / 0.5)
        since = min((t - b for b in BEATS if b <= t), default=9)
        s = (0.9 + 0.1 * a) * (1 + 0.02 * math.exp(-since * 8))  # логотип отзывается на доли
        size = int(LOGO_R * 2 * s)
        im = self.img.resize((size, size), Image.BILINEAR)
        k = (t % 4.0) / 0.9
        if self.glint and 0 < k < 1 and t > 1:
            band = Image.new("L", (size, size), 0)
            x = -120 + k * (size + 240)
            ImageDraw.Draw(band).polygon([(x, 0), (x + 70, 0), (x + 70 - size * .5, size), (x - size * .5, size)], fill=120)
            band = ImageChops.multiply(band.filter(ImageFilter.GaussianBlur(14)), self.mask.resize((size, size)))
            light = Image.new("RGBA", (size, size), (255, 255, 255, 0)); light.putalpha(band)
            im.alpha_composite(light)
        if a < 1:
            im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        fr.alpha_composite(im, (LOGO_C[0] - size // 2, LOGO_C[1] - size // 2))


# ---------- раскладка ----------

def slot_rows(slots, single_column):
    if single_column:
        return [[s] for s in slots]
    rows, pair = [], []
    for sl in slots:  # «13:30 или 14:00» и непарная плашка — отдельной строкой
        if "или" in sl:
            if pair: rows.append(pair); pair = []
            rows.append([sl])
        else:
            pair.append(sl)
            if len(pair) == 2: rows.append(pair); pair = []
    if pair: rows.append(pair)
    return rows


def wrap(text, f, width):
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if cur and textlen(test, f) > width:
            lines.append(cur); cur = word
        else:
            cur = test
    return lines + [cur] if cur else lines


def build(style, date, slots, slogan, pal, phrase=None):
    els, pills = [], []

    def label(text, f, cx, cy, start, dark=INK):
        w = textlen(text, f)
        color, halo = pal.text((cx - w / 2, cy - f.size / 2, cx + w / 2, cy + f.size / 2), dark)
        els.append(El(text_sprite(text, f, color, halo), cx, cy, start))

    n = len(slots)
    if style == "lines":
        label("СВОБОДНОЕ ВРЕМЯ", font(80), W / 2, 330, 0.3, ACCENT)
        y = 415
        if phrase:  # фраза дня от Ивана вместо подзаголовка
            f = font(42)
            for i, ln in enumerate(wrap(phrase, f, 900)[:3]):
                label(ln, f, W / 2, y, 0.6 + 0.18 * i); y += 54
            y -= 54
        else:
            label("«Гладкие линии» · лазерная эпиляция", font(44), W / 2, y, 0.6)
        label(f"{date.day} {MONTHS[date.month - 1]}", font(112), W / 2, y + 130, 1.1)
        label(DAYS[date.weekday()], font(56), W / 2, y + 245, 1.3)
        top, t_slot = y + 345, 1.9
    else:
        f = font(44); y = 190
        slogan = phrase.upper() if phrase else slogan
        for i, ln in enumerate(wrap(slogan, f, 720)):
            label(ln, f, W / 2, y, 0.7 + 0.18 * i); y += 56
        top, t_slot = y + 40, 0.9 + 0.18 * len(wrap(slogan, f, 720))

    single = n <= 4
    ph, gap = (110, 28) if single else ((92, 24) if n <= 8 else (80, 18))
    tf = font(64 if single else (52 if n <= 8 else 46))
    j = 0
    for r, row in enumerate(slot_rows(slots, single)):
        cy = top + r * (ph + gap) + ph / 2
        for c, sl in enumerate(row):
            if len(row) == 1:
                pw, cx, kind = max(400, textlen(sl, tf) + 190), W / 2, "up"
            else:
                pw, cx, kind = 410, W / 2 + (c - 0.5) * 440, ("left", "right")[c]
            light = pal.light((cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2))
            img, mask = pill_sprite(pw, ph, sl, tf, style, light)
            e = El(img, cx, cy, t_slot + (0.3 if style == "lines" else 0.13) * j,
                   "rise" if style == "lines" else kind, mask, pulse=True)
            els.append(e); pills.append(e); j += 1

    t0 = t_slot + (0.3 if style == "lines" else 0.13) * j + 0.2
    if style == "lines":
        for i, (txt, sz, yy) in enumerate([("Запись:", 44, 1480), ("+7 (905) 537-27-07", 50, 1545),
                                            ("ул. Дмитриевского, 3", 40, 1620), ("бесплатная парковка", 36, 1675)]):
            label(txt, font(sz), RIGHT_X, yy, t0 + 0.15 * i)
    else:
        day = DAYS[date.weekday()].upper()
        for i, (txt, sz, yy) in enumerate([(str(date.day), 66, 1410), (MONTHS[date.month - 1].upper(), 66, 1492),
                                            (day, 58 if len(day) < 10 else 46, 1572),
                                            ("СВОБОДНОЕ", 58, 1672), ("ВРЕМЯ", 58, 1745)]):
            label(txt, font(sz), RIGHT_X, yy, t0 + 0.15 * i)
    return els, pills


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="ГГГГ-ММ-ДД")
    p.add_argument("--slots", nargs="+", required=True, help='время, например 11:00 "13:30 или 14:00"')
    p.add_argument("--picture", help="картинка или видео для фона")
    p.add_argument("--slogan", help="своя фраза дня")
    p.add_argument("--style", choices=["lines", "glass"], help="по умолчанию чередуются по дням")
    p.add_argument("-o", "--out", default="slot.mp4")
    a = p.parse_args()
    date = dt.date.fromisoformat(a.date)
    k = date.toordinal()
    pics = pictures()
    src = a.picture or pics[k % len(pics)]
    bg = VideoBg(src) if src.lower().endswith((".mp4", ".mov")) else PictureBg(src)
    style = a.style or ("glass", "lines")[k % 2]
    pal = Palette(bg.still(DUR / 2))

    with tempfile.TemporaryDirectory() as tmp:
        track = MUSIC[k % len(MUSIC)] if MUSIC else music.compose(DUR, k, os.path.join(tmp, "music.wav"))
        BEATS[:] = beats(track)
        els, pills = build(style, date, a.slots[:10], SLOGANS[k % len(SLOGANS)], pal, a.slogan)
        # надписи появляются в такт: момент появления притягивается к ближайшей доле или полудоле
        grid = sorted(set(BEATS + [(x + y) / 2 for x, y in zip(BEATS, BEATS[1:])]))
        for e in els:
            e.start = snap(e.start, grid)
        logo, sparkles = Logo(glint=style == "glass"), Sparkles(k) if style == "glass" else None
        downbeats = BEATS[4::4]
        cmd = [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-stream_loop", "-1", "-i", track, "-map", "0:v", "-map", "1:a",
               "-af", f"afade=t=in:d=0.5,afade=t=out:st={DUR - 1.5}:d=1.5", "-c:a", "aac", "-b:a", "128k",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18",
               "-movflags", "+faststart", "-shortest", a.out]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for i in range(int(DUR * FPS)):
            t = i / FPS
            fr = bg.frame(t)
            if style == "lines":
                waves(fr, t)
            logo.draw(fr, t)
            for e in els:
                e.draw(fr, t)
            if style == "glass":
                for j, e in enumerate(pills):  # блики по плашкам на сильные доли
                    for db in downbeats:
                        if db > 3.5:
                            e.glint(fr, t, db + 0.06 * j)
                sparkles.draw(fr, t)
            proc.stdin.write(fr.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait():
            raise SystemExit("ffmpeg error")
    print(a.out)


if __name__ == "__main__":
    main()
